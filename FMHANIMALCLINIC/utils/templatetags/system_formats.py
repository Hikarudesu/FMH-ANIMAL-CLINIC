"""Template date and time filters using the configured system formats."""

import re

from django.template import Library
from django.template.defaultfilters import date as django_date
from django.template.defaultfilters import time as django_time
from django.utils import timezone

from settings.utils import get_setting

register = Library()


def _configured_date_format(format_string):
    if format_string in {'Y-m-d', 'c', 'r', 'U'}:
        return format_string

    date_format = get_setting('system_date_format', 'M d, Y')
    time_format = get_setting('system_time_format', 'h:i A')
    tokens = re.sub(r'\\.', '', format_string or '')
    has_day = any(token in tokens for token in 'djDlSwz')
    if not has_day:
        return format_string or date_format

    has_time = any(token in tokens for token in 'aAgGhHisueOPTZ')
    return f'{date_format} {time_format}' if has_time else date_format


@register.filter(name='date', expects_localtime=True)
def system_date(value, format_string=None):
    """Format full dates with the superadmin's system date and time formats."""
    return django_date(value, _configured_date_format(format_string))


@register.filter(name='time', expects_localtime=True)
def system_time(value, format_string=None):
    """Format displayed times with the superadmin's system time format."""
    configured_format = get_setting('system_time_format', 'h:i A')
    return django_time(value, configured_format)


@register.filter(name='machine_time', expects_localtime=True)
def machine_time(value):
    """Keep a time value in the 24-hour format required by JavaScript controls."""
    return django_time(value, 'H:i')


@register.simple_tag(name='now')
def system_now(format_string):
    """Use the configured date format for Django's current-date template tag."""
    return django_date(
        timezone.localtime(timezone.now()),
        _configured_date_format(format_string),
    )