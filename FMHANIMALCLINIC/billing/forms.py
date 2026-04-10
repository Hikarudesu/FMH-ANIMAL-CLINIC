"""
Forms for the billing app — clinic services only.
"""
from django import forms
from FMHANIMALCLINIC.form_mixins import FormControlMixin
from .models import Service


class ServiceForm(FormControlMixin, forms.ModelForm):
    """Form for creating and updating clinic services."""
    class Meta:
        """Meta configuration for ServiceForm."""
        model = Service
        fields = [
            'name', 'cost', 'price', 'branch', 'category',
            'tax_rate', 'duration', 'description', 'active', 'content'
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'placeholder': 'e.g., General Consultation'
            }),
            'cost': forms.NumberInput(attrs={'step': '0.01'}),
            'price': forms.NumberInput(attrs={'step': '0.01'}),
            'branch': forms.Select(attrs={'class': 'form-select'}),
            'category': forms.TextInput(attrs={
                'placeholder': 'e.g., Consultation, Surgery, Grooming'
            }),
            'tax_rate': forms.TextInput(attrs={
                'placeholder': 'e.g., VAT 12%'
            }),
            'duration': forms.NumberInput(attrs={
                'placeholder': 'Minutes'
            }),
            'description': forms.Textarea(attrs={
                'rows': 3,
                'placeholder': 'Describe the service...'
            }),
            'active': forms.CheckboxInput(attrs={'role': 'switch'}),
            'content': forms.Textarea(attrs={
                'rows': 5,
                'placeholder': 'Instructions, notes, or content...'
            }),
        }
