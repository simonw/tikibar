Tikibar
=======

A debugging and information toolbar for django, designed for lightweight impact
so it can be enabled selectively and run in production.

Features
--------

Among other things, it includes:

* CPU usage time statistics
* Used template tracking
* SQL call logging and timing
* Cross-domain functionality

Installation
------------

First, add tikibar to your installed apps and middleware:

    INSTALLED_APPS = (
        ...
        'tikibar',
    )

    MIDDLEWARE = (
        ...
        'tikibar.middleware.SetCorrelationIDMiddleware',
        'tikibar.middleware.TikibarMiddleware',
        ...
    )

The `SetCorrelationIDMiddleware` sets a request.correlation_id property. You can
use your own middleware for this instead if you already have a correlation ID
concept implemented.

To enable template logging, switch your template backend to this:

    TEMPLATES = [{
        'BACKEND': 'tikibar.template_backend.TikibarDjangoTemplates',
        ...
    }]

Add this to your settings:

    TIKIBAR_SETTINGS = {
        "blacklist": [],
    }

Next, add the following to your URL configuration:

    from django.urls import re_path, include
    import tikibar.views

    tikibar_patterns = [
        re_path(r'^$', tikibar.views.tikibar),
        re_path(r'^settings/$', tikibar.views.tikibar_settings),
        re_path(r'^on/$', tikibar.views.tikibar_on),
        re_path(r'^set-for-api-domain/$', tikibar.views.tikibar_set_for_api_domain),
        re_path(r'^off/$', tikibar.views.tikibar_off),
    ]

    url_patterns = [
        # Your patterns here
        re_path(r'^tikibar/', include(tikibar_patterns)),
    ]

Tikibar uses the Django default cache, so make sure you have configured that to
something sensible (probably memcached or redis).

To turn on the Tikibar, sign in as a Django staff user and visit `/tikibar/on/`
- then turn it on.

Version Compatibility
---------------------

This branch of tikibar requires Django 2.0 or higher.
