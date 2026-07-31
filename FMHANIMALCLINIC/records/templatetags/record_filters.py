"""
Custom template filters for the records app.
Used primarily to prepare text for xhtml2pdf rendering.
"""
from django import template
from django.utils.html import conditional_escape
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter
def format_date_str(value):
    """
    Format a date string (YYYY-MM-DD) as a human-readable date, e.g. "Jan 15, 2020".
    If the value cannot be parsed as a date it is returned unchanged.
    """
    if not value:
        return value
    from datetime import date
    try:
        d = date.fromisoformat(str(value).strip())
        return f"{d.strftime('%b')} {d.day}, {d.year}"
    except (ValueError, TypeError):
        return value


@register.filter
def get_item(dictionary, key):
    """Return dictionary[key], or None if key is missing. Useful for dict lookups in templates."""
    if isinstance(dictionary, dict):
        return dictionary.get(key)
    return None


@register.filter(is_safe=True, needs_autoescape=True)
def break_long_words(value, autoescape=True):
    """
    Insert <br> tags every 18 characters inside any word that has no natural
    break point. xhtml2pdf does not support word-break: break-all in CSS, so
    this filter forces word-wrapping at the HTML content level.

    Also preserves newlines by converting them to <br>.
    """
    if not value:
        return value

    escape = conditional_escape if autoescape else lambda x: x
    max_chunk = 14  # Reduced to fit narrower Tx/Rx columns

    lines = str(value).splitlines()
    output_lines = []

    for line in lines:
        words = line.split(' ')
        broken_words = []
        for word in words:
            escaped_word = escape(word)
            if len(word) > max_chunk:
                # Break every max_chunk characters
                chunks = []
                while len(escaped_word) > max_chunk:
                    chunks.append(escaped_word[:max_chunk])
                    escaped_word = escaped_word[max_chunk:]
                chunks.append(escaped_word)
                broken_words.append('<br>'.join(chunks))
            else:
                broken_words.append(escaped_word)
        output_lines.append(' '.join(broken_words))

    return mark_safe('<br>'.join(output_lines))
