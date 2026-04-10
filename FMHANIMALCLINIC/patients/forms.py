from django import forms
from django.db.models import Q
from FMHANIMALCLINIC.form_mixins import validate_philippines_phone
from .models import Pet


class PetForm(forms.ModelForm):
    """Form for creating and editing a pet (user portal)."""

    class Meta:
        model = Pet
        fields = ['photo', 'name', 'species', 'breed', 'date_of_birth', 'sex', 'color', 'is_active']
        widgets = {
            'photo': forms.ClearableFileInput(attrs={
                'class': 'pf-input', 'accept': 'image/*'
            }),
            'name': forms.TextInput(attrs={
                'class': 'pf-input', 'placeholder': ' ',
            }),
            'species': forms.TextInput(attrs={
                'class': 'pf-input', 'placeholder': ' ', 'oninput': 'if(this.value.length > 0) this.value = this.value.charAt(0).toUpperCase() + this.value.slice(1);'
            }),
            'breed': forms.TextInput(attrs={
                'class': 'pf-input', 'placeholder': ' ', 'oninput': 'if(this.value.length > 0) this.value = this.value.charAt(0).toUpperCase() + this.value.slice(1);'
            }),
            'date_of_birth': forms.DateInput(attrs={
                'class': 'pf-input', 'type': 'date',
            }),
            'sex': forms.Select(attrs={
                'class': 'pf-input',
            }),
            'color': forms.TextInput(attrs={
                'class': 'pf-input', 'placeholder': ' ',
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'pf-checkbox',
            }),
        }


class AdminPetForm(forms.ModelForm):
    """
    Admin form for creating and editing a patient.

    Supports two modes controlled by the ``source`` field:
    - PORTAL: owner is selected from registered portal users.
    - WALKIN: guest owner plain-text fields are filled in instead.
    """
    
    def clean_species(self):
        species = self.cleaned_data.get('species')
        if species:
            return species[0].upper() + species[1:]
        return species

    def clean_breed(self):
        breed = self.cleaned_data.get('breed')
        if breed:
            return breed[0].upper() + breed[1:]
        return breed

    class Meta:
        model = Pet
        fields = [
            'source',
            # Portal owner
            'owner',
            # Guest owner fields
            'guest_owner_name', 'guest_owner_phone',
            'guest_owner_email', 'guest_owner_address',
            # Pet details
            'photo', 'name', 'species', 'breed',
            'date_of_birth', 'sex', 'clinical_status', 'color', 'is_active',
        ]
        widgets = {
            'source': forms.Select(attrs={'class': 'pf-input', 'id': 'id_source'}),
            'owner': forms.Select(attrs={'class': 'pf-input'}),
            'guest_owner_name': forms.TextInput(attrs={'class': 'pf-input', 'placeholder': 'Full name of the owner'}),
            'guest_owner_phone': forms.TextInput(attrs={
                'class': 'pf-input',
                'placeholder': '09XXXXXXXXX',
                'inputmode': 'numeric',
                'pattern': '[0-9]{11}',
                'minlength': '11',
                'maxlength': '11',
                'oninput': "this.value=this.value.replace(/\\D/g,'')",
            }),
            'guest_owner_email': forms.EmailInput(attrs={'class': 'pf-input', 'placeholder': 'owner@email.com'}),
            'guest_owner_address': forms.Textarea(attrs={'class': 'pf-input', 'rows': 2, 'placeholder': 'Full address'}),
            'photo': forms.ClearableFileInput(attrs={'class': 'pf-input', 'accept': 'image/*'}),
            'name': forms.TextInput(attrs={'class': 'pf-input', 'placeholder': 'Pet name'}),
            'species': forms.TextInput(attrs={'class': 'pf-input', 'placeholder': 'e.g. Dog, Cat, Bird', 'oninput': 'if(this.value.length > 0) this.value = this.value.charAt(0).toUpperCase() + this.value.slice(1);'}),
            'breed': forms.TextInput(attrs={'class': 'pf-input', 'placeholder': 'e.g. Labrador', 'oninput': 'if(this.value.length > 0) this.value = this.value.charAt(0).toUpperCase() + this.value.slice(1);'}),
            'date_of_birth': forms.DateInput(attrs={'class': 'pf-input', 'type': 'date'}),
            'sex': forms.Select(attrs={'class': 'pf-input'}),
            'clinical_status': forms.Select(attrs={'class': 'pf-input'}),
            'color': forms.TextInput(attrs={'class': 'pf-input', 'placeholder': 'e.g. Brown, Black/White'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'pf-checkbox'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from django.contrib.auth import get_user_model
        User = get_user_model()
        # Show only portal/pet-owner accounts in the owner dropdown.
        # This excludes staff/admin/veterinary accounts.
        self.fields['owner'].queryset = User.objects.filter(
            is_active=True
        ).filter(
            Q(assigned_role__is_staff_role=False) | Q(assigned_role__isnull=True)
        ).distinct().order_by('first_name', 'last_name', 'username')
        self.fields['owner'].required = False
        self.fields['owner'].empty_label = '— Select Portal Account User —'
        # Customize the label for the owner dropdown
        self.fields['owner'].label_from_instance = lambda obj: (
            f"{obj.get_full_name()} ({obj.username})"
            if obj.get_full_name().strip() else obj.username
        )
        # Guest fields are not required by default; validation enforces them conditionally
        for f in ['guest_owner_name', 'guest_owner_phone', 'guest_owner_email', 'guest_owner_address']:
            self.fields[f].required = False

        # Set up clinical_status with dynamic choices
        from settings.models import ClinicalStatus
        self.fields['clinical_status'].queryset = ClinicalStatus.objects.filter(is_active=True).order_by('order', 'name')
        self.fields['clinical_status'].label = 'Clinical Status'
        self.fields['clinical_status'].empty_label = '-- Select Status --'
        self.fields['clinical_status'].required = False

        # Make source field read-only when editing existing pet to prevent data loss
        if self.instance and self.instance.pk:
            self.fields['source'].disabled = True
            self.fields['source'].help_text = 'Patient type cannot be changed after registration to prevent data loss.'
            
            # For editing, show all statuses including inactive ones
            self.fields['clinical_status'].queryset = ClinicalStatus.objects.all().order_by('order', 'name')

            # Also disable the opposite owner type fields based on current source
            if self.instance.source == Pet.Source.PORTAL:
                # Disable guest fields for portal patients
                for f in ['guest_owner_name', 'guest_owner_phone', 'guest_owner_email', 'guest_owner_address']:
                    self.fields[f].disabled = True
            elif self.instance.source == Pet.Source.WALKIN:
                # Disable owner field for walk-in patients
                self.fields['owner'].disabled = True

    def clean_species(self):
        species = self.cleaned_data.get('species')
        if species:
            return species[0].upper() + species[1:]
        return species

    def clean_breed(self):
        breed = self.cleaned_data.get('breed')
        if breed:
            return breed[0].upper() + breed[1:]
        return breed

    def clean(self):
        cleaned = super().clean()

        # When editing, source field is disabled so use instance value
        if self.instance and self.instance.pk:
            source = self.instance.source
        else:
            source = cleaned.get('source')

        owner = cleaned.get('owner')
        guest_name = cleaned.get('guest_owner_name', '').strip()

        if source == Pet.Source.PORTAL:
            # Only validate and clear if this is a new record (not editing)
            if not self.instance or not self.instance.pk:
                if not owner:
                    self.add_error('owner', 'Please select a registered owner for portal patients.')
                # Clear guest fields when source is PORTAL
                cleaned['guest_owner_name'] = ''
                cleaned['guest_owner_phone'] = ''
                cleaned['guest_owner_email'] = ''
                cleaned['guest_owner_address'] = ''
        elif source == Pet.Source.WALKIN:
            # Only validate and clear if this is a new record (not editing)
            if not self.instance or not self.instance.pk:
                if not guest_name:
                    self.add_error('guest_owner_name', 'Owner name is required for walk-in patients.')
                # Validate phone using centralized function
                phone = cleaned.get('guest_owner_phone', '').strip()
                if phone:
                    try:
                        validate_philippines_phone(phone)
                    except forms.ValidationError as e:
                        self.add_error('guest_owner_phone', e)
                # Clear portal owner when source is WALKIN
                cleaned['owner'] = None
            else:
                # When editing walk-in patient, still validate phone if it's being changed
                phone = cleaned.get('guest_owner_phone', '').strip()
                if phone:
                    try:
                        validate_philippines_phone(phone)
                    except forms.ValidationError as e:
                        self.add_error('guest_owner_phone', e)

        return cleaned
    
    def save(self, commit=True):
        instance = super().save(commit=False)
        if commit:
            instance.save()
        return instance
