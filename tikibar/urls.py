from django.conf.urls import url

urlpatterns = [
    url(r'^$', 'tikibar.views.tikibar'),
    url(r'^settings/$', 'tikibar.views.tikibar_settings'),
    url(r'^on/$', 'tikibar.views.tikibar_on'),
    url(r'^set-for-api-domain/$', 'tikibar.views.tikibar_set_for_api_domain'),
    url(r'^off/$', 'tikibar.views.tikibar_off'),
]