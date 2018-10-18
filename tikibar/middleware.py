import json
import os
import resource
import time
import threading
import uuid

from django.conf import settings
from django.core.cache import cache
from django.utils.deprecation import MiddlewareMixin
from .sampler import Sampler

from .utils import (
    _should_show_tikibar_for_request,
    get_tiki_token_or_false,
    tikibar_feature_flag_enabled,
    set_tikibar_active_on_response,
    TIKIBAR_DATA_STORAGE_TIMEOUT,
)


__current_instances = threading.local()


def set_current_request(request):
    """Store the current request for use by feature flag evaluation."""

    __current_instances.request = request


def get_current_request():
    """Return the thread's current request, if any."""

    return getattr(__current_instances, 'request', None)


def clear_current_request():
    """Clear the current request."""

    __current_instances.request = None


class SetCorrelationIDMiddleware(MiddlewareMixin):
    def process_request(self, request):
        # Add a correlation id to the request (needed later)
        request.correlation_id = uuid.uuid1(
            node=uuid.getnode(),
            clock_seq=None
        ).hex
        return None


class TikibarMiddleware(MiddlewareMixin):
    def process_request(self, request):
        from .toolbar_metrics import get_toolbar
        # set the request on tikibar's context
        set_current_request(request)
        if tikibar_feature_flag_enabled(request):
            toolbar = get_toolbar()
            if toolbar.is_active():
                if settings.TIKIBAR_SETTINGS.get('enable_profiler'):
                    profile_interval = settings.TIKIBAR_SETTINGS.get('profile_interval', 0.01)
                    request.sampler = Sampler(interval=profile_interval)
                    request.sampler.start()
                rusage = resource.getrusage(resource.RUSAGE_SELF)
                if not hasattr(request, 'req_start_time'):
                    request.req_start_time = time.time()
                if not hasattr(request, 'utime_start'):
                    request.utime_start = rusage.ru_utime
                if not hasattr(request, 'stime_start'):
                    request.stime_start = rusage.ru_stime
                if not hasattr(request, 'maxrss_start'):
                    request.maxrss_start = rusage.ru_maxrss
        return None

    def process_view(self, request, view_func, view_args, view_kwargs):
        from .toolbar_metrics import get_toolbar
        if not tikibar_feature_flag_enabled(request):
            return None

        toolbar = get_toolbar()
        if toolbar.is_active():
            toolbar.set_view_callable(view_func)

        return None

    def process_response(self, request, response):
        from .toolbar_metrics import get_toolbar
        if not tikibar_feature_flag_enabled(request):
            return response

        toolbar = get_toolbar()
        # hasattr handles edge case where is_active is false in process_request but true here
        if toolbar.is_active() and hasattr(request, 'req_start_time'):
            setattr(request, 'req_stop_time', time.time())
            rusage = resource.getrusage(resource.RUSAGE_SELF)
            # convert kB to MB
            rss_growth = (rusage.ru_maxrss - request.maxrss_start) / 1000
            toolbar.add_singular_metric('total_time', {'d': [request.req_start_time, request.req_stop_time]})
            toolbar.add_singular_metric('user_cpu', {'d': [request.utime_start, rusage.ru_utime]})
            toolbar.add_singular_metric('system_cpu', {'d': [request.stime_start, rusage.ru_stime]})
            toolbar.add_singular_metric('rss_growth', rss_growth)
            toolbar.add_singular_metric('release', getattr(settings, 'RELEASE', 'master'))
            toolbar.add_singular_metric('request_path', request.get_full_path())
            if settings.TIKIBAR_SETTINGS.get('enable_profiler'):
                toolbar.add_stack_samples(request.sampler.output_stats())
                toolbar.add_singular_metric('stack_sample_count', request.sampler.sample_count())
                request.sampler.stop()
            toolbar.write_metrics()
            if response.get('content-type', '').startswith('text/html')\
                    and response.content \
                    and not response.get('x-suppress-tikibar')\
                    and not getattr(request, 'is_varnish_populating_cache', False):
                content = response.content
                content = content.replace(
                    b'</head>', ('<meta name="correlation_id" value="{}"></head>'.format(
                        request.correlation_id.encode("utf8")
                    )).encode("utf8")
                )
                # TODO: Figure out a staticfiles implementation that
                # works for this.
                script_str = '<script>window.TIKI_PROTOCOL = "{protocol}";</script>\n'.format(
                    protocol='http' if (settings.DEBUG and not request.is_secure()) else 'https'
                )
                with open(os.path.join(os.path.dirname(__file__), 'static/js/tikibar.js'), 'r') as js:
                    script_str += '<script type="text/javascript" charset="utf-8">{}</script>'.format(
                        js.read()
                    )
                    content = content.replace(
                        b'</body>', (script_str + '</body>').encode("utf8")
                    )
                    response.content = content

            request_duration = (request.req_stop_time - request.req_start_time)
            # And add the headers
            response['X-Tiki-Time'] = request_duration
            response['X-Correlation-ID'] = request.correlation_id

            # Add correlation ID to list of most recent 20 correlation IDs
            # in memcached. Note that this has a race condition which could be
            # solved using memcached cas (or a Redis list), but in practice
            # doesn't actually matter.
            tiki_token = get_tiki_token_or_false(request)
            if tiki_token and not response.get('x-suppress-tikibar'):
                cache_key = 'tikibar:history:%s' % tiki_token
                current = cache.get(cache_key) or ''
                if current:
                    current_list = json.loads(current)
                else:
                    current_list = []

                # JSON blob with metadata about request
                current_list.append({
                    'd': request_duration,
                    't': request.req_start_time,
                    'u': request.get_full_path(),
                    'c': request.correlation_id,
                    'v': request.method,
                    's': response.status_code,
                })
                current_list = current_list[-15:]
                cache.set(cache_key, json.dumps(
                    current_list,
                ), TIKIBAR_DATA_STORAGE_TIMEOUT)
        else:
            if request.is_secure() or settings.DEBUG:
                if _should_show_tikibar_for_request(request):
                    set_tikibar_active_on_response(response, request)

        # Note: Process response will be called even in case of exceptions,
        # Django will catch exceptions, call process_exception,
        # and then call process_response in the end. Hence it is safe to clear
        # it here, and not in process_exception.
        clear_current_request()

        return response
