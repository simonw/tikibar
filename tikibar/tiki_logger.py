import logging


class TikiLogHandler(logging.Handler):
        def __init__(self,):
            # run the regular Handler __init__
            logging.Handler.__init__(self)

        def emit(self, record):
            # Needs to import here because of a dependency on
            # feature flags, which are not available at app startup
            from .toolbar_metrics import get_toolbar
            toolbar = get_toolbar()
            if toolbar.is_active():
                toolbar.add_freeform_metric(
                    'loglines',
                    (record.levelname, getattr(record, 'message', ''))
                )
