import os
import uuid
import urlparse
import logging
from functools import wraps

from django.conf import settings
from django.http import HttpResponse, HttpResponsePermanentRedirect, Http404

TIKIBAR_DATA_STORAGE_TIMEOUT = 3000 # time to store cache data
TIKI_COOKIE = 'tikibar_active'
TIKIBAR_VIEW_COOKIE_NAME = 'tikiok'
TIKI_SALT_HTTPS = 'tiki-salt-extra-https'
TIKI_COOKIE_ENABLED_EXPIRATION = 60 * 60  # 60 minutes, in seconds
TIKI_COOKIE_DISABLED_EXPIRATION = 30 * 24 * 60 * 60  # 30 days, in seconds
TIKIBAR_DISABLED_STRING = 'disabled'


def get_tiki_token_or_false_for_tikibar_view(request):
    # This function gets the tikitoken, and then verifies
    # it against the the TIKIBAR_VIEW_COOKIE_NAME. See the comments
    # in the tikibar view to understand why this is the way
    # it is.
    #
    # Note that when enabling the tikibar, if we EVER set the
    # TIKIBAR_VIEW_COOKIE_NAME cookie on a non-HTTPS connection,
    # we lose the security properties of this.
    tiki_token = get_tiki_token_or_false(request)
    if not tiki_token:
        return False

    # Now, let's grab the TIKIBAR_VIEW_COOKIE_NAME against this
    # value. We hope to find the same tiki_token in this
    # HTTPS-only cookie. If we don't, then it's also a good idea
    # to return False.
    #
    # Note that we use a salt here because otherwise we'd be
    # vulnerable to the following attack:
    #
    # - Attacker steals valid tikitoken cookie, then
    # - Inserts it into the browser with secure=True, then
    # - Sends that to this view, where we would
    # - Validate the signature (which passes).
    #
    # We need to make sure that a valid HTTP cookie can't be
    # used as a HTTPS cookie for the purpose of this view,
    # so we use a salt.
    tiki_token_from_https = request.get_signed_cookie(
        TIKIBAR_VIEW_COOKIE_NAME,
        salt=TIKI_SALT_HTTPS,
        default=False,
        max_age=TIKI_COOKIE_ENABLED_EXPIRATION,
    )

    if not tiki_token_from_https:
        # Well, it failed a signature check, or it was missing.
        return False

    if tiki_token == tiki_token_from_https:
        # Hooray! We successfully used the HTTPS-only cookie to
        # validate the tikitoken cookie. This means that we
        # confirm that they're not using a stolen tikitoken.
        return tiki_token_from_https

    # If we made it this far, then nothing worked.
    return False


def tikibar_feature_flag_enabled(request):
    try:
        from gargoyle import gargoyle
        return gargoyle.is_active(settings.TIKIBAR, request)
    except ImportError:
        if hasattr(settings, 'ENABLE_TIKIBAR'):
            return settings.ENABLE_TIKIBAR
        if settings.DEBUG:
            return settings.DEBUG
    return False


def get_tiki_token_or_false(request):
    # NOTE: The tikibar view does not use this function. In general,
    # the output of this function should not be used to let the user
    # *see* data in the tikibar.
    #
    # It's totally OK to take the return value from this function and
    # use it in the following ways:
    #
    # - Calculating a cache key for *storing* data that the tikibar
    #   view will display, and
    # - Sending the token back to the user, such as in the IFRAME URL
    #   that comprises the tikibar.
    if _should_collect_tiki_data_for_request(request):
        # Attempt to calculate the token_value out of the signed cookie in
        # the request. Cache this on the request so it isn't computed multiple
        # times.
        if not hasattr(request, '_tiki_token_value'):
            request._tiki_token_value = request.get_signed_cookie(
                TIKI_COOKIE,
                default=False,
                max_age=TIKI_COOKIE_ENABLED_EXPIRATION,
            )
        # If the user has no token_value, or no valid token value, then the
        # tikibar is not enabled.
        if request._tiki_token_value:
            return request._tiki_token_value
    return False


def set_tikibar_active_on_response(response, request):
    # Tikibar is only available over HTTPS. Callers to this function
    # should (and do, at the time of writing) check this.

    # First, generate a token. We'll use this in memcached as the identifier
    # for this site visitor's data in the tikibar.
    token_value = _create_random_token()
    # We store this token, plus Django secure-cookie signing metadata, in the
    # response's cookie set. We set the "secure" property to indicate that
    response.set_signed_cookie(
        TIKI_COOKIE,
        token_value,
        domain=settings.TIKIBAR_SETTINGS.get('domain'),
        secure=False,
    )

    if request.is_secure() or settings.DEBUG:
        response.set_signed_cookie(
            TIKIBAR_VIEW_COOKIE_NAME,
            salt=TIKI_SALT_HTTPS,
            value=token_value,
        )


def set_tikibar_disabled_by_user(response):
    response.set_signed_cookie(
        TIKI_COOKIE,
        TIKIBAR_DISABLED_STRING,
        secure=True,
    )


def _create_random_token():
    return uuid.uuid4().hex


def _should_collect_tiki_data_for_request(request):
    # Cache the value of this on the request, so it isn't calculated every time.
    if not hasattr(request, '_collect_tikibar_data_for_request'):
        enabled_cookie = request.get_signed_cookie(
            TIKI_COOKIE,
            default=False,
            max_age=TIKI_COOKIE_ENABLED_EXPIRATION,
        )
        disabled_cookie = request.get_signed_cookie(
            TIKI_COOKIE,
            default=False,
            max_age=TIKI_COOKIE_DISABLED_EXPIRATION,
        )

        for path in settings.TIKIBAR_SETTINGS.get('blacklist'):
            if request.path.startswith(path):
                request._collect_tikibar_data_for_request = False
        if enabled_cookie and enabled_cookie != TIKIBAR_DISABLED_STRING:
            request._collect_tikibar_data_for_request = True
        if disabled_cookie and disabled_cookie == TIKIBAR_DISABLED_STRING:
            request._collect_tikibar_data_for_request = False
        if not hasattr(request, '_collect_tikibar_data_for_request'):
            request._collect_tikibar_data_for_request = False

    return request._collect_tikibar_data_for_request


def _should_show_tikibar_for_request(request):
    # Cache the value of this on the request, so it isn't calculated every time.
    if not hasattr(request, '_show_tikibar_for_request'):
        if (
            hasattr(request, '_collect_tikibar_data_for_request') 
            and request._collect_tikibar_data_for_request
        ):
            request._show_tikibar_for_request = tikibar_feature_flag_enabled(request)
        else:
            request._show_tikibar_for_request = False
    return request._show_tikibar_for_request


def find_view_subpath(full_path):
    # First, find the absolute path of the full path
    full_path_abs = os.path.realpath(full_path)

    # Then, find absolute path of current releases, etc
    filepath = settings.TIKIBAR_SETTINGS.get('filepath')
    if filepath:
        codebase_top_level_abs = os.path.realpath(filepath)

        # Make sure we're where we think we are and subtract
        if full_path_abs.startswith(codebase_top_level_abs):
            return full_path_abs[len(codebase_top_level_abs) + 1:]

        # But if we're not, at least log an error
        logging.warn(
            "Tikibar: View filepath not as expected %s %s",
            full_path_abs,
            codebase_top_level_abs,
        )

    return ''


def format_analytics_action_for_tikibar(action_data):
    """Given a dictionary of AnalyticsAction data, format it for presentation in tikibar.
    """
    data = []
    for key in sorted(action_data):
        data.append('{key}:{value}'.format(key=key, value=action_data[key]))
    return '\n'.join(data)


def ssl_required(function):
    """Decorator for SSL. If the request is not made over SSL,
       redirect to SSL.

    """
    def decorator(view_func):

        def _wrapped_view(request, *args, **kwargs):
            if request.is_secure():
                return view_func(request, *args, **kwargs)
            if not settings.DEBUG:
                parsed = urlparse.urlparse(request.build_absolute_uri())
                https_url = urlparse.urlunparse((
                    'https',
                    parsed.netloc,
                    parsed.path,
                    parsed.params,
                    parsed.query,
                    parsed.fragment
                ))
                return HttpResponsePermanentRedirect(https_url)
            else:
                return view_func(request, *args, **kwargs)

        return wraps(view_func)(_wrapped_view)

    return decorator(function)


