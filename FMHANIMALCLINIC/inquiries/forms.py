from django import forms
from .models import Inquiry


class InquirySubmitForm(forms.ModelForm):
    """Form for public contact form submission."""
    
    class Meta:
        model = Inquiry
        fields = ['full_name', 'email', 'phone', 'branch', 'message']
        widgets = {
            'full_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Your name',
                'autocomplete': 'name'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'your.email@example.com',
                'autocomplete': 'email'
            }),
            'phone': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '09XXXXXXXXX',
                'inputmode': 'numeric',
                'pattern': '[0-9]{11}',
                'maxlength': '11',
                'autocomplete': 'tel'
            }),
            'branch': forms.Select(attrs={
                'class': 'form-control'
            }),
            'message': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 6,
                'placeholder': 'Tell us more about your message...'
            }),
        }
    
    def clean_phone(self):
        phone = self.cleaned_data.get('phone', '')
        # Remove any non-digit characters
        phone = ''.join(filter(str.isdigit, phone))
        if len(phone) != 11:
            raise forms.ValidationError('Phone number must be exactly 11 digits')
        return phone


class InquiryResponseForm(forms.ModelForm):
    """Form for admin to respond to inquiries."""
    
    class Meta:
        model = Inquiry
        fields = ['status', 'priority', 'response', 'internal_notes']
        widgets = {
            'status': forms.Select(attrs={
                'class': 'form-control'
            }),
            'priority': forms.Select(attrs={
                'class': 'form-control'
            }),
            'response': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 6,
                'placeholder': 'Type your response to the customer...'
            }),
            'internal_notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Internal notes (not visible to customer)'
            }),
        }
