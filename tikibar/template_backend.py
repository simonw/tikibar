from django.template.backends.django import DjangoTemplates
from tikibar.toolbar_metrics import get_toolbar
import time


class TikibarDjangoTemplates(DjangoTemplates):
    def get_template(self, template_name):
        start = time.time()
        result = super().get_template(template_name)
        get_toolbar().add_timed_metric(
            'templates', template_name, start, time.time()
        )
        return result
