from django import template
from django.conf import settings
from django.core.files.storage import default_storage
from django.templatetags.static import static

register = template.Library()


@register.filter
def stored_or_static_url(file_field):
    """Use private media for new files and static storage for legacy files."""
    if not file_field:
        return ''
    name = getattr(file_field, 'name', '')
    if not name:
        return ''
    if default_storage.exists(name):
        return file_field.url
    try:
        return static(name)
    except ValueError:
        # A legacy filename may not be present in WhiteNoise's manifest.
        return f"{settings.STATIC_URL.rstrip('/')}/{name.lstrip('/')}"
