from django import template

register = template.Library()


@register.filter
def stored_or_static_url(file_field):
    """Return the uploaded media URL directly for valid file fields.

    We intentionally avoid enforcing an existence check here so the app renders the
    image path saved in the database instead of silently suppressing a valid upload.
    """
    if not file_field:
        return ''

    name = getattr(file_field, 'name', '')
    if not name:
        return ''

    return getattr(file_field, 'url', '') or ''
