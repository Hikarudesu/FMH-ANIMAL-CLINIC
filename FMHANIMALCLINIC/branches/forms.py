from django import forms
from FMHANIMALCLINIC.form_mixins import FormControlMixin, validate_philippines_phone
from .models import Branch


class BranchForm(FormControlMixin, forms.ModelForm):
    """Form for creating and updating Branch instances."""

    class Meta:
        model = Branch
        fields = [
            'name', 'branch_code', 'clinic_license_number',
            'phone_number', 'email',
            'address', 'city', 'state', 'zip_code',
            'operating_hours', 'is_active',
            'google_maps_embed_url', 'google_maps_link',
            'facebook_url', 'instagram_url', 'messenger_url', 'tiktok_url',
            'display_order', 'badge_label',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'e.g. Downtown Clinic'}),
            'branch_code': forms.TextInput(attrs={'placeholder': 'e.g. DWTN'}),
            'clinic_license_number': forms.TextInput(attrs={'placeholder': 'License/Registration number'}),
            'phone_number': forms.TextInput(attrs={
                'placeholder': '09XXXXXXXXX',
                'inputmode': 'numeric',
                'pattern': '[0-9]{11}',
                'minlength': '11',
                'maxlength': '11',
                'oninput': "this.value=this.value.replace(/\\D/g,'')",
            }),
            'email': forms.EmailInput(attrs={'placeholder': 'Email address'}),
            'address': forms.TextInput(attrs={'placeholder': 'Street Address'}),
            'city': forms.TextInput(attrs={'placeholder': 'City'}),
            'state': forms.TextInput(attrs={'placeholder': 'State/Province'}),
            'zip_code': forms.TextInput(attrs={'placeholder': 'Zip/Postal Code'}),
            'operating_hours': forms.Textarea(attrs={'rows': 3, 'placeholder': 'e.g. Mon-Fri: 8am-6pm, Sat: 9am-2pm'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-checkbox'}),
            'google_maps_embed_url': forms.URLInput(attrs={
                'placeholder': 'https://www.google.com/maps/embed?pb=...',
                'help_text': 'Go to Google Maps → Share → Embed a map → Copy the src URL'
            }),
            'google_maps_link': forms.URLInput(attrs={
                'placeholder': 'https://maps.app.goo.gl/...'
            }),
            'facebook_url': forms.URLInput(attrs={'placeholder': 'Facebook page URL'}),
            'instagram_url': forms.URLInput(attrs={'placeholder': 'Instagram profile URL'}),
            'messenger_url': forms.URLInput(attrs={'placeholder': 'Messenger URL'}),
            'tiktok_url': forms.URLInput(attrs={'placeholder': 'TikTok profile URL'}),
            'display_order': forms.NumberInput(attrs={'placeholder': '0'}),
            'badge_label': forms.TextInput(attrs={'placeholder': 'e.g. Main Branch, New!'}),
        }

    def clean_phone_number(self):
        return validate_philippines_phone(self.cleaned_data.get('phone_number', ''))
