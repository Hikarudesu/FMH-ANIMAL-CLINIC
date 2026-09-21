from django import template
from django.conf import settings
from django.core.files.storage import default_storage
from django.templatetags.static import static

register = template.Library()


@register.filter
def stored_or_static_url(file_field):
    """Return the media URL only when the uploaded file actually exists.

    Do not silently fall back to a static file with the same name. When a DB path
    points to a missing upload, the correct behavior is to surface the missing file
    rather than masking it with a different static asset.
    """
    if not file_field:
        return ''

    name = getattr(file_field, 'name', '')
    if not name:
        return ''

    if default_storage.exists(name):
        return file_field.url

    return ''
