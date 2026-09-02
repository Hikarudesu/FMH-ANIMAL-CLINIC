"""
Custom template filters
Usage: {{ value|peso }}, {{ date1|same_date:date2 }}
"""

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from django import template
from datetime import date, datetime

register = template.Library()


def format_overtime_duration(value):
    """Return OT in a human-friendly format.

    Values under 1 hour are shown as minutes, e.g. 0.0667 -> 4 mins.
    Values at or above 1 hour are shown in hours, e.g. 1.5 -> 1.5 hrs.
    """
    if value in (None, ''):
        return '0 mins'

    try:
        hours = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return '0 mins'

    total_minutes = (hours * Decimal('60')).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
    if hours < Decimal('1'):
        return f'{int(total_minutes)} mins'

    hours_rounded = hours.quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)
    text = format(hours_rounded, 'f').rstrip('0').rstrip('.')
    return f'{text} hrs'


@register.filter(name='peso')
def peso(value):
    """Format a number as Philippine peso with thousands separator and 2 decimal places."""
    if value is None or value == '':
        return '0.00'
    try:
        return f'{float(value):,.2f}'
    except (ValueError, TypeError):
        return '0.00'


@register.filter(name='same_date')
def same_date(value, compare_to):
    """Check if two dates are the same (ignoring time for datetime objects)."""
    if value is None or compare_to is None:
        return False
    
    # Convert datetime to date if necessary
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(compare_to, datetime):
        compare_to = compare_to.date()
    
    return value == compare_to


@register.filter(name='is_today')
def is_today(value):
    """Check if a date is today."""
    if value is None:
        return False
    
    # Convert datetime to date if necessary
    if isinstance(value, datetime):
        value = value.date()
    
    return value == date.today()


@register.filter(name='overtime_duration')
def overtime_duration(value):
    """Show overtime as minutes below 1 hour and hours otherwise."""
    return format_overtime_duration(value)
