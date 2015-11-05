import logging


class TikiLogHandler(logging.Handler): # Inherit from logging.Handler
        def __init__(self,):
            # run the regular Handler __init__
            logging.Handler.__init__(self)

        def emit(self, record):
            # Needs to import here because of a dependency on
            # feature flags, which are not available at app startup
            from .toolbar_metrics import get_toolbar
            toolbar = get_toolbar()
            if toolbar.is_active():
                if record.name == 'analytics_logger':
                    # Currently all log data that comes in through
                    # 'web_analytics' log is sent to the toolbar in the
                    # AnalyticsStorageLogger in common/analytics/__init__.py.
                    # Once we port the legacy AnalyticsActions over to the new
                    # format, we'll include those here but doing so now would
                    # double count them. The actions are also all bundled
                    # together in one flat dict at this point.  It will be
                    # easier to add them to the tikibar once they're logged
                    # individually.  At that point we'll add them
                    # if record.name in ('analytics_logger' , 'web_analytics')
                    msg = getattr(record, 'msg', None)
                    if msg:
                        toolbar.add_analytics_action_metric(msg)
                else:
                    toolbar.add_freeform_metric(
                        'loglines',
                        (record.levelname, getattr(record, 'message', ''))
                    )
