from django.conf.urls import url
from tikibar import views

urlpatterns = [
    url(r'^$', views.tikibar),
    url(r'^settings/$', views.tikibar_settings),
    url(r'^on/$', views.tikibar_on),
    url(r'^set-for-api-domain/$', views.tikibar_set_for_api_domain),
    url(r'^off/$', views.tikibar_off),
]