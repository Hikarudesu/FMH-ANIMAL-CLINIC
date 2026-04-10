"""
Custom template filters
Usage: {{ value|peso }}, {{ date1|same_date:date2 }}
"""

from django import template
from datetime import date, datetime

register = template.Library()


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
