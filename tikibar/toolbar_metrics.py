from collections import defaultdict
import importlib
import inspect
import logging
import re

from django.core.cache import cache

from .middleware import get_current_request
from .utils import (
    get_tiki_token_or_false,
    TIKIBAR_DATA_STORAGE_TIMEOUT,
    find_view_subpath,
    format_dict_as_lines,
)


def publish_toolbar_metrics(correlation_id, metrics):
    cache_key = "tikibar:%s" % (correlation_id)
    cache.set(cache_key, metrics, TIKIBAR_DATA_STORAGE_TIMEOUT)


def get_toolbar():
    """Create and Return persistent MetricsContainer on the current request"""
    container = None
    request = get_current_request()
    if not request:
        return ToolbarMetricsContainer('no-correlation-id-because-no-request', False)

    if not hasattr(request, 'correlation_id'):
        return ToolbarMetricsContainer('no-correlation-id', False)

    # Toolbar active state is dictated by signed cookie
    is_active = bool(get_tiki_token_or_false(request))

    if request and not getattr(request, 'toolbar_metrics', None):
        container = ToolbarMetricsContainer(request.correlation_id, is_active)
        request.toolbar_metrics = container
    else:
        container = request.toolbar_metrics

    return container


class ToolbarMetricsContainer:

    # If the metrics are longer than this, they'll be dropped in an
    # attempt to fit into memcached
    max_size = 1000 * 1024

    def __init__(self, correlation_id, is_active=True):
        self.metrics = defaultdict(list)
        self.metrics['queries'] = defaultdict(list)
        self.correlation_id = correlation_id
        self._is_active = is_active

    def is_active(self):
        return self._is_active

    def set_view_callable(self, view_func):
        module = view_func.__module__
        filepath = importlib.import_module(module).__file__
        if filepath.endswith('.pyc'):
            filepath = filepath[:-4] + '.py'
        try:
            view_func_s = view_func.__name__ + inspect.formatargspec(*inspect.getargspec(view_func))
        except Exception:
            view_func_s = str(view_func)

        self.add_singular_metric('view', view_func_s)
        self.add_singular_metric(
            'view_filepath',
            find_view_subpath(filepath),
        )

    def add_timed_metric(self, metric_type, val, start, stop):
        self.metrics[metric_type].append((val, {'d': (start, stop)}))

    def add_query_metric(self, metric_type, query_type, val, start, stop, needs_format=False):
        self.metrics['queries'][metric_type].append(
            (query_type, val, needs_format, {'d': (start, stop)})
        )

    def add_sql_query_metric(self, query_type, val, start, stop):
        self.add_query_metric(
            metric_type='SQL',
            query_type=query_type,
            val=val,
            start=start,
            stop=stop,
            needs_format=True,
        )

    def add_freeform_metric(self, metric_type, data):
        self.metrics[metric_type].append(data)

    def add_singular_metric(self, metric_type, data):
        self.metrics[metric_type] = data

    def add_stack_samples(self, samples):
        self.metrics['stack_samples'] = samples

    def write_metrics(self):
        # If the metrics seem too long, start dropping parts to try and fit
        if len(repr(self.metrics)) > self.max_size:
            self.metrics["loglines"] = [("ERROR", "Logs too big for memcached")]
        if len(repr(self.metrics)) > self.max_size:
            self.metrics["queries"]["SQL"] = [
                (
                    query_type,
                    re.sub(r"/\*.+\*/", "", val)[:50] + "...",
                    needs_format,
                    timing,
                )
                for query_type, val, needs_format, timing in self.metrics["queries"]["SQL"]
            ]
        if len(repr(self.metrics)) > self.max_size:
            self.metrics["queries"]["SQL"] = [
                (query_type, "", needs_format, timing)
                for query_type, val, needs_format, timing in self.metrics["queries"]["SQL"]
            ]
        publish_toolbar_metrics(self.correlation_id, self.metrics)
