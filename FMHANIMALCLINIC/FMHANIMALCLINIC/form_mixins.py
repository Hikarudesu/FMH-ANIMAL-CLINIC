"""
Reusable form mixins that auto-apply CSS classes to all fields.

Usage:
    class MyForm(FormControlMixin, forms.ModelForm):
        ...

    class MySettingsForm(AdminInputMixin, forms.Form):
        ...
"""
from django import forms


# Widget types that should get checkbox-style classes instead of input classes
_CHECKBOX_WIDGETS = (forms.CheckboxInput, forms.CheckboxSelectMultiple)


def validate_philippines_phone(value):
    """
    Validate Philippine phone numbers (11 digits, usually starting with 09).

    Args:
        value (str): The phone number to validate

    Returns:
        str: The cleaned phone number

    Raises:
        forms.ValidationError: If the phone number is invalid
    """
    if not value:
        return value

    cleaned_value = value.strip()

    if len(cleaned_value) != 11:
        raise forms.ValidationError('Phone number must be exactly 11 digits.')

    if not cleaned_value.isdigit():
        raise forms.ValidationError('Phone number must contain only digits.')

    if not cleaned_value.startswith('09'):
        raise forms.ValidationError('Phone number must start with 09.')

    return cleaned_value


class FormControlMixin:
    """Adds 'form-control' to all fields, 'form-check-input' to checkboxes."""

    css_class = 'form-control'
    checkbox_css_class = 'form-check-input'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, _CHECKBOX_WIDGETS):
                _add_css_class(widget, self.checkbox_css_class)
            elif isinstance(widget, forms.FileInput):
                _add_css_class(widget, self.css_class)
            else:
                _add_css_class(widget, self.css_class)


class AdminInputMixin:
    """Adds 'admin-input' to all fields, 'admin-checkbox' to checkboxes."""

    css_class = 'admin-input'
    checkbox_css_class = 'admin-checkbox'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, _CHECKBOX_WIDGETS):
                _add_css_class(widget, self.checkbox_css_class)
            else:
                _add_css_class(widget, self.css_class)


def _add_css_class(widget, css_class):
    """Add a CSS class to a widget's attrs, preserving any existing classes."""
    existing = widget.attrs.get('class', '')
    if css_class not in existing.split():
        widget.attrs['class'] = f"{existing} {css_class}".strip()
