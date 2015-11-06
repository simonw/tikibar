from django.core import signing
from django.http import HttpResponse, HttpResponseRedirect, Http404
from django import template
from django.conf import settings
from django.core.cache import cache
from django.utils.encoding import smart_bytes
from django.utils.html import escape
from .utils import (
    get_tiki_token_or_false,
    set_tikibar_active_on_response,
    set_tikibar_disabled_by_user,
    tikibar_feature_flag_enabled,
    get_tiki_token_or_false_for_tikibar_view,
    ssl_required,
)
import json, hashlib, itertools, time, os

from .sql_utils import reformat_sql

TIKI_ANGER_THRESHOLD = 500 # 500ms

TIKI_BAR_COLORS = ['#8adb1e', '#1c4dcb', '#b21ccb', '#f53522', '#f5aa22', '#e7f021']

def tiki_response(response):
    response['x-suppress-tikibar'] = '1'
    setattr(response, 'xframe_option', 'EXEMPT')
    return response

@ssl_required
def tikibar_settings(request):
    if not tikibar_feature_flag_enabled(request):
        raise Http404, 'Tikibar is turned off'
    if not request.user or not request.user.is_staff:
        raise Http404, 'Staff required'
    is_active = bool(get_tiki_token_or_false(request))
    t = template.loader.get_template('tikibar/tikibar_settings.html')
    return HttpResponse(t.render(template.RequestContext(request, {
        'is_active': is_active,
    })))


@ssl_required
def tikibar(request):
    if not tikibar_feature_flag_enabled(request):
        return tiki_response(HttpResponse('Tikibar is turned off'))

    # Check for a HTTPS-only cookie called 'tikiok', which allows
    # the user to see the bar.
    #
    # It should be bound to the actual tikitoken, to avoid the following
    # attack:
    #
    # - Person enables tikibar for themselves, and then
    # - gets a valid 'tikok' cookie, and then
    # - steals someone else's tikitoken cookie, and then
    # - requests the tikibar, which lets them spy on someone else's requests.
    #
    # This is not a HUGE problem, in terms of an attack, since typically
    # we would only enable the tikibar for admins, but it's nice to be
    # resistant to this attack in case others down the road want to
    # enable the tikibar for non-admin users.
    #
    # (Side note: a SEPARATE cookie is used to store the value of the
    # the tikitoken. We use Django's signed cookies to make sure that
    # cookie wasn't tampered with.)
    tiki_token = get_tiki_token_or_false_for_tikibar_view(request)
    if not tiki_token:
        return tiki_response(HttpResponse('No tiki-token!'))

    correlation_id = request.GET.get('correlation_id', '')
    if not correlation_id:
        return tiki_response(HttpResponse(''))

    data = cache.get('tikibar:%s' % correlation_id)

    history_cache_key = 'tikibar:history:%s' % tiki_token
    request_history = json.loads(cache.get(history_cache_key) or '[]')
    request_history.reverse()
    request_history = [r for r in request_history if r['c'] != correlation_id]

    if data:
        data['correlation_id'] = correlation_id
        data['request_history'] = request_history
        data['release_hash'] = data['release'].split('-')[-1]

        now = time.time()
        for row in data['request_history']:
            row['ago'] = now - row['t']
            row['ms'] = row['d'] * 1000

        # Massage data
        def expand_durations(obj):
            if isinstance(obj, dict) and obj.keys()[0] == 'd':
                return duration(obj)
            elif isinstance(obj, dict):
                return dict([(key, expand_durations(value)) for key, value in obj.items()])
            elif isinstance(obj, list) or isinstance(obj, tuple):
                return [expand_durations(item) for item in obj]
            else:
                return obj
        data = expand_durations(data)

        total_time = data['total_time']['duration']

        soa = {}
        total_soa_time = 0

        for service, timing in data.get('soa', []):
            soa[service] = timing['duration']
            total_soa_time += soa[service]

        queries = []

        for query_type, sql, timing in data.get('sql_query', []):
            queries.append({
                'sql': reformat_sql(sql),
                'type': query_type,
                'timing': timing,
            })

        for cql, timing in data.get('cassandra_cql', []):
            queries.append({
                'sql': reformat_sql(cql),
                'type': 'cassandra',
                'timing': timing,
            })
        for query, timing in data.get('solr', []):
            queries.append({
                'sql': repr(query),
                'type': 'solr',
                'timing': timing,
            })
        sum_sql = sum([q['timing']['duration'] for q in queries])

        for service, timing in data.get('soa', []):
            queries.append({
                'sql': service,
                'type': 'soa',
                'timing': timing,
            })

        queries.sort(key=lambda x: x['timing']['start'])
        # Next annotate queries with the visual styling information we need
        left = 0
        for query in queries:
            query['bar'] = {}
            query['bar']['left'] = left
            query['bar']['width'] = (query['timing']['duration'] / (sum_sql + total_soa_time)) * 100
            left += query['bar']['width']
            query['color'] = hashlib.md5(smart_bytes(query['sql'])).hexdigest()[:6]

        data['queries'] = queries
        data['sum_sql'] = sum_sql

        # Add funky slashes to the template paths
        templates = []
        for tmpl in data.get('django_template_load', []):
            # There's probably a better to selectively prepend the correct directory.
            template_name = tmpl[0]
            if template_name[0] != '/':
                template_name = '/' + template_name
            if 'templates' not in template_name:
                filepath = 'django/templates' + template_name
            else:
                filepath = 'django' + template_name
            templates.append({
                'filepath': filepath,
                'timing': tmpl[1],
                'filepath_with_slashes': slasherize(filepath),
            })
        for tmpl in data.get('core_template_render', []):
            filepath = 'django/templates_core/' + tmpl[0]
            templates.append({
                'filepath': filepath,
                'timing': tmpl[1],
                'filepath_with_slashes': slasherize(filepath),
            })
        for tmpl in data.get('handlebars_template_render', []):
            filepath = 'django/media/django/js/' + tmpl[0]
            templates.append({
                'filepath': filepath,
                'timing': tmpl[1],
                'filepath_with_slashes': slasherize(filepath),
            })
        templates.sort(key = lambda x: x['timing']['start'])
        data['templates'] = templates

        # Colourful bars - currently just SQL, SOA calls, and Other
        bars = []
        bars.append({
            'name': 'SQL',
            'ms': sum_sql
        })
        bars.append({
            'name': 'SOA calls',
            'ms': total_soa_time,
        })
        bars.append({
            'name': 'Other',
            'ms': (total_time - sum_sql - total_soa_time),
        })
        nextcol = itertools.cycle(TIKI_BAR_COLORS)
        for bar in bars:
            bar['color'] = next(nextcol)
            bar['width'] = (bar['ms'] / total_time) * 100
        data['bars'] = bars

        if data.get('view_filepath'):
            data['view_filepath_with_slashes'] = slasherize(data['view_filepath'])

        if total_time > TIKI_ANGER_THRESHOLD:
            data['angry'] = True

    if request.GET.get('render'):
        template_name = 'tikibar.html'
        if request.GET.get('template') == 'minibar':
            template_name = 'minibar.html'
        t = template.loader.get_template('tikibar/%s' % template_name)
        return tiki_response(HttpResponse(t.render(template.RequestContext(request, {'tiki': data}))))
    else:
        return tiki_response(HttpResponse(json.dumps(data, indent=2), content_type='application/json'))

@ssl_required
def tikibar_on(request):

    if not request.user or not request.user.is_staff:
        return HttpResponse('You must be signed in as staff')

    if request.method == 'POST':
        response = HttpResponseRedirect('/tikibar/settings/?set_for_api_domain=1')
        set_tikibar_active_on_response(response, request)
        return response
    else:
        t = template.loader.get_template('tikibar/tikibar_on.html')
        return HttpResponse(t.render(template.RequestContext(request, {})))

@ssl_required
def tikibar_off(request):
    if not tikibar_feature_flag_enabled(request):
        raise Http404, 'Tikibar is turned off'
    if request.method == 'POST':
        response = HttpResponse("""
            Tikibar is now off<script>window.parent.postMessage(JSON.stringify({'tiki_msg_type': 'hide'}), '*');</script>
        """)
        # response.delete_cookie('tikibar_active')
        set_tikibar_disabled_by_user(response)
        return tiki_response(response)
    else:
        t = template.loader.get_template('tikibar/tikibar_off.html')
        return tiki_response(HttpResponse(t.render(template.RequestContext(request, {}))))

def duration(obj):
    return {
        'start': obj['d'][0],
        'end': obj['d'][1],
        'duration': (obj['d'][1] - obj['d'][0]) * 1000
    }


def slasherize(path):
    bits = [escape(bit) for bit in path.split('/')]
    return '<span class="tiki-slash">/</span>'.join(bits)


@ssl_required
def set_token_cross_domain(request):
    # No check for tikibar_feature_flag_enabled() due to lack of auth cookies used by feature flag
    nonce = request.GET.get('nonce')
    if not nonce:
        return HttpResponse('Could not set, no nonce')
    try:
        signer = signing.TimestampSigner()
        key = signer.unsign(nonce, max_age=10).split(r'tikibar-nonce:')[1]
        # We return a 1x1 transparent gif, since we're triggered by an <img src="">
        gif = "R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7".decode('base64')
        response = HttpResponse(gif, content_type = 'image/gif')
        set_tikibar_active_on_response(response, request)
        return response
    except:
        return HttpResponse('Could not set, invalid nonce')


@ssl_required
def tikibar_set_for_api_domain(request):
    if not tikibar_feature_flag_enabled(request):
        raise Http404, 'Tikibar is turned off'
    if not request.user or not request.user.is_staff:
        return HttpResponse('You must be signed in as staff')
    api_domain = settings.EBAPIDOMAIN
    nonce = os.urandom(16).encode('hex')
    key = 'tikibar-nonce:%s' % nonce
    signer = signing.TimestampSigner()
    return HttpResponseRedirect('https://%s/tikibar/set-token/?nonce=%s' % (api_domain, signer.sign(key)))
