"""
WSGI config for FMHANIMALCLINIC project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.0/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application
from whitenoise import WhiteNoise

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'FMHANIMALCLINIC.settings')

application = get_wsgi_application()

# Wrap the application with WhiteNoise to serve static and media files
# This is essential for production deployments where Gunicorn doesn't serve files
from django.conf import settings
application = WhiteNoise(
    application,
    root=str(settings.STATIC_ROOT),
    mimetypes=settings.WHITENOISE_MIMETYPES,
)

# Add media files directory to WhiteNoise so they're served from /media/ URL
if settings.MEDIA_ROOT and settings.MEDIA_URL:
    application.add_files(str(settings.MEDIA_ROOT), prefix=settings.MEDIA_URL.lstrip('/'))

