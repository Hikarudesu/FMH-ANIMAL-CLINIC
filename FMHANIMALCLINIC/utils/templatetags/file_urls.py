from django import template
from django.core.files.storage import default_storage
from django.contrib.staticfiles import finders
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
    if finders.find(name) is None:
        return ''
    return static(name)
