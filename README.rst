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


Getting Started
---------------

To use Tikibar, you need to add it to your Django ``INSTALLED_APPS`` and then
include the middleware (``tikibar.middleware.TikibarMiddleware``) in your
Django middleware configuration.


Version Compatibility
---------------------

Tikibar is currently only tested against Django 1.5, and will likely not work
against Django 1.11 due to the new middleware format.
