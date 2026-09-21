"""
WSGI config for FMHANIMALCLINIC project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.0/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'FMHANIMALCLINIC.settings')

application = get_wsgi_application()

# WhiteNoiseMiddleware (in MIDDLEWARE) only serves STATIC_ROOT. Gunicorn has
# no built-in static/media file serving, so uploaded media (profile photos,
# pet photos, service photos) stored on the /app/media volume would 404 in
# production without this. Wrap the WSGI app with a second WhiteNoise layer
# rooted at MEDIA_ROOT so it is served under MEDIA_URL regardless of DEBUG.
try:
    from whitenoise import WhiteNoise

    from django.conf import settings

    application = WhiteNoise(
        application,
        root=str(settings.MEDIA_ROOT),
        prefix=settings.MEDIA_URL.lstrip('/'),
    )
except ImportError:
    pass
