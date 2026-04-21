"""
Forms for the appointments app.
"""
# pylint: disable=no-member


from datetime import time, date
from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from FMHANIMALCLINIC.form_mixins import FormControlMixin, validate_philippines_phone

from branches.models import Branch
from employees.models import StaffMember, VetSchedule

from .models import Appointment


PET_SEX_CHOICES = [
    ('', '---'),
    ('MALE', 'Male'),
    ('FEMALE', 'Female'),
]


def _validate_appointment_date(appt_date, allow_past=False):
    """
    Validate that the appointment date is not in the past.

    Args:
        appt_date: The date to validate
        allow_past: If True, allow past dates (used for admin forms)
    """
    if not appt_date or allow_past:
        return
    today = timezone.localdate()
    if appt_date < today:
        raise ValidationError(
            'Appointment date cannot be in the past. Please select a future date.'
        )


def _validate_vet_schedule(branch, appt_date, vet=None):
    """Validate that there are vets scheduled at the branch on the date."""
    if not branch or not appt_date:
        return

    # Check if there are any scheduled vets for this branch and date
    scheduled_vet_ids = list(VetSchedule.objects.filter(
        branch=branch,
        date=appt_date,
        is_available=True,
    ).values_list('staff_id', flat=True).distinct())

    if not scheduled_vet_ids:
        raise ValidationError(
            'No veterinarians are scheduled at this branch on the selected date. '
            'Please choose a different date or branch.'
        )

    # If a specific vet was selected, ensure they are scheduled
    if vet:
        if vet.id not in scheduled_vet_ids:
            raise ValidationError(
                f'{vet.full_name} is not scheduled at this branch on the selected date. '
                'Please choose a different vet or date.'
            )


def _check_double_booking(cleaned_data, allow_past=False, instance_id=None):
    """
    Shared validation: reject if the vet+date+time slot is already booked.
    
    Args:
        cleaned_data: Form cleaned data
        allow_past: If True, allow past dates (used for admin forms)
        instance_id: Optional appointment ID to exclude from conflict checking.
    """
    vet = cleaned_data.get('preferred_vet')
    appt_date = cleaned_data.get('appointment_date')
    appt_time = cleaned_data.get('appointment_time')
    branch = cleaned_data.get('branch')

    if not appt_date or not appt_time or not branch:
        return  # other validators will catch missing required fields

    # Validate appointment date is not in the past (skip for admin editing)
    _validate_appointment_date(appt_date, allow_past=allow_past)

    # Validate vets are scheduled at this branch on this date
    _validate_vet_schedule(branch, appt_date, vet)

    if time(12, 0) <= appt_time < time(13, 0):
        raise ValidationError(
            'Appointments cannot be scheduled between 12:00 PM and 1:00 PM (Lunch Break).'
        )

    if vet:
        # Specific vet selected — check if that vet is already booked
        conflict_query = Appointment.objects.filter(
            preferred_vet=vet,
            appointment_date=appt_date,
            appointment_time=appt_time,
        ).exclude(status='CANCELLED')
        
        if instance_id:
            conflict_query = conflict_query.exclude(pk=instance_id)
            
        if conflict_query.exists():
            raise ValidationError(
                'This time slot is already booked for this veterinarian. '
                'Please select a different time.'
            )
    else:
        # No vet selected ("any available") — check if ALL scheduled vets
        # at this branch+date+time are booked
        scheduled_vet_ids = list(VetSchedule.objects.filter(
            branch=branch,
            date=appt_date,
            is_available=True,
        ).values_list('staff_id', flat=True).distinct())

        if scheduled_vet_ids:
            booked_query = Appointment.objects.filter(
                appointment_date=appt_date,
                appointment_time=appt_time,
                preferred_vet_id__in=scheduled_vet_ids,
            ).exclude(status='CANCELLED')
            
            if instance_id:
                booked_query = booked_query.exclude(pk=instance_id)
                
            booked_vet_ids = list(booked_query.values_list(
                'preferred_vet_id', flat=True
            ))

            if set(scheduled_vet_ids) == set(booked_vet_ids):
                raise ValidationError(
                    'All veterinarians are fully booked at this time. '
                    'Please select a different time slot.'
                )


class PublicAppointmentForm(FormControlMixin, forms.ModelForm):
    """Booking form for public visitors (no login required)."""
    
    # Use CharField to intercept "MORNING"/"AFTERNOON" text before TimeField validation
    appointment_time = forms.CharField(
        widget=forms.Select(choices=[('', '-- Select a time slot --')]),
        required=True,
    )

    # Explicitly declare reason as ModelChoiceField to work with ReasonForVisit ForeignKey
    reason = forms.ModelChoiceField(
        queryset=None,  # Will be set in __init__
        required=True,
        empty_label='-- Select Reason --',
        widget=forms.Select()
    )

    class Meta:
        """Form metadata."""
        model = Appointment
        fields = [
            'owner_name', 'owner_email', 'owner_phone', 'owner_address',
            'pet_name', 'pet_species', 'pet_breed', 'pet_dob', 'pet_sex', 'pet_color',
            'pet_symptoms',
            'branch', 'preferred_vet',
            'appointment_date', 'appointment_time',
        ]
        widgets = {
            'owner_name': forms.TextInput(attrs={'placeholder': 'Your full name'}),
            'owner_email': forms.EmailInput(attrs={'placeholder': 'email@example.com'}),
            'owner_phone': forms.TextInput(attrs={
                'placeholder': '09XXXXXXXXX',
                'inputmode': 'numeric',
                'pattern': '[0-9]{11}',
                'minlength': '11',
                'maxlength': '11',
                'oninput': "this.value=this.value.replace(/\\D/g,'')",
            }),
            'owner_address': forms.Textarea(attrs={
                'rows': 2, 'placeholder': 'Your full address',
            }),
            'pet_name': forms.TextInput(attrs={'placeholder': "Your pet's name", 'oninput': 'if(this.value.length === 1) this.value = this.value.toUpperCase(); else if(this.value.length > 0) this.value = this.value.charAt(0).toUpperCase() + this.value.slice(1);'}),
            'pet_species': forms.TextInput(attrs={'placeholder': 'e.g. Dog, Cat, Bird', 'oninput': 'if(this.value.length === 1) this.value = this.value.toUpperCase(); else if(this.value.length > 0) this.value = this.value.charAt(0).toUpperCase() + this.value.slice(1);'}),
            'pet_breed': forms.TextInput(attrs={'placeholder': 'e.g. Golden Retriever', 'oninput': 'if(this.value.length === 1) this.value = this.value.toUpperCase(); else if(this.value.length > 0) this.value = this.value.charAt(0).toUpperCase() + this.value.slice(1);'}),
            'pet_dob': forms.DateInput(attrs={'type': 'date'}),
            'pet_sex': forms.Select(choices=PET_SEX_CHOICES),
            'pet_color': forms.TextInput(attrs={'placeholder': 'e.g. Brown, White', 'oninput': 'if(this.value.length === 1) this.value = this.value.toUpperCase(); else if(this.value.length > 0) this.value = this.value.charAt(0).toUpperCase() + this.value.slice(1);'}),
            'pet_symptoms': forms.Textarea(attrs={
                'rows': 3,
                'placeholder': 'Please describe any symptoms or reasons for visit',
            }),
            'branch': forms.Select(),
            'preferred_vet': forms.Select(),
            'appointment_date': forms.DateInput(attrs={'type': 'date'}),
            'appointment_time': forms.Select(choices=[('', '-- Select a time slot --')]),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['branch'].queryset = Branch.objects.filter(is_active=True)
        self.fields['preferred_vet'].queryset = StaffMember.objects.none()
        self.fields['preferred_vet'].required = False
        self.fields['preferred_vet'].empty_label = '-- Any Available Vet --'
        self.fields['pet_species'].required = False
        self.fields['pet_breed'].required = False
        self.fields['pet_dob'].required = False
        self.fields['pet_sex'].required = False
        self.fields['pet_color'].required = False
        self.fields['pet_symptoms'].required = False
        self.fields['owner_email'].required = False
        self.fields['owner_phone'].required = False
        self.fields['owner_address'].required = False
        
        # Set up reason with dynamic choices (mapped to reason_for_visit backend)
        from settings.models import ReasonForVisit
        self.fields['reason'].queryset = ReasonForVisit.objects.filter(is_active=True).order_by('order', 'name')
        self.fields['reason'].label = 'Reason for Visit'
        # empty_label is already set in field declaration

        # Schedulable roles: veterinarians and vet assistants
        schedulable_roles = ['veterinarian', 'vet_assistant']

        if 'branch' in self.data:
            try:
                branch_id = int(self.data.get('branch'))
                appt_date = self.data.get('appointment_date')

                # If date is provided, get vets/vet assistants scheduled at this branch on this date
                # This matches the API behavior (api_available_vets)
                if appt_date:
                    scheduled_staff_ids = VetSchedule.objects.filter(
                        branch_id=branch_id,
                        date=appt_date,
                        is_available=True,
                    ).values_list('staff_id', flat=True).distinct()

                    self.fields['preferred_vet'].queryset = StaffMember.objects.filter(
                        id__in=scheduled_staff_ids,
                        user__assigned_role__code__in=schedulable_roles,
                        is_active=True,
                    ).select_related('user', 'user__assigned_role')
                else:
                    # No date - return vets/vet assistants assigned to this branch
                    self.fields['preferred_vet'].queryset = StaffMember.objects.filter(
                        user__assigned_role__code__in=schedulable_roles,
                        is_active=True,
                        branch_id=branch_id,
                    ).select_related('user', 'user__assigned_role')
            except (ValueError, TypeError):
                pass

    def clean(self):
        cleaned_data = super().clean()
        # Handle MORNING/AFTERNOON markers for any available vet mode
        time_str = self.data.get('appointment_time')
        if time_str == 'MORNING':
            cleaned_data['appointment_time'] = time(8, 0)
        elif time_str == 'AFTERNOON':
            cleaned_data['appointment_time'] = time(13, 0)
            
        _check_double_booking(cleaned_data)
        return cleaned_data

    def clean_appointment_time(self):
        """
        Parse time from Select widget.
        Accepts:
        - HH:MM format for specific time slots
        - "MORNING" marker for any available morning slot (defaults to 08:00)
        - "AFTERNOON" marker for any available afternoon slot (defaults to 13:00)
        """
        time_str = self.data.get('appointment_time', '')
        if not time_str:
            raise ValidationError('Please select a time slot.')
        
        # Handle MORNING/AFTERNOON markers for "any available vet" mode
        if time_str == 'MORNING':
            return time(8, 0)  # Default morning time, vet will be assigned later
        elif time_str == 'AFTERNOON':
            return time(13, 0)  # Default afternoon time, vet will be assigned later
        
        try:
            hours, minutes = map(int, time_str.split(':'))
            return time(hours, minutes)
        except (ValueError, AttributeError):
            raise ValidationError('Invalid time format. Please select a valid time slot.')

    def clean_appointment_date(self):
        """Validate appointment date is not in the past."""
        appt_date = self.cleaned_data.get('appointment_date')
        if appt_date:
            _validate_appointment_date(appt_date)
        return appt_date

    def clean_owner_phone(self):
        return validate_philippines_phone(self.cleaned_data.get('owner_phone', ''))

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.source = Appointment.Source.WALKIN

        # Map the 'reason' field (ModelChoiceField) to 'reason_for_visit' ForeignKey
        if 'reason' in self.cleaned_data:
            reason_obj = self.cleaned_data['reason']
            instance.reason_for_visit = reason_obj
        
        # Check if the user selected 'yes' on the special returning client radio buttons in HTML
        is_returning = self.data.get('is_returning') == 'yes'
        instance.is_returning_customer = is_returning

        # Do not auto-assign vet if none was selected to preserve ANY VET option

        if commit:
            instance.save()
            # Auto-create / link a walk-in Patient record
            from .utils import sync_pet_from_appointment
            sync_pet_from_appointment(instance)
        return instance


class PortalAppointmentForm(FormControlMixin, forms.ModelForm):
    """Booking form for logged-in portal users."""

    css_class = 'form-control book-input'

    # Hidden field for selected pet ID
    selected_pet_id = forms.IntegerField(required=False, widget=forms.HiddenInput())
    
    # Use CharField to intercept "MORNING"/"AFTERNOON" text before TimeField validation
    appointment_time = forms.CharField(
        widget=forms.Select(choices=[('', '-- Select a time slot --')]),
        required=True,
    )

    # Explicitly declare reason as ModelChoiceField to work with ReasonForVisit ForeignKey
    reason = forms.ModelChoiceField(
        queryset=None,  # Will be set in __init__
        required=True,
        empty_label='-- Select Reason --',
        widget=forms.Select()
    )

    class Meta:
        """Form metadata."""
        model = Appointment
        fields = [
            'owner_name', 'owner_email', 'owner_phone', 'owner_address',
            'pet_name', 'pet_species', 'pet_breed', 'pet_dob', 'pet_sex', 'pet_color',
            'pet_symptoms',
            'branch', 'preferred_vet',
            'appointment_date', 'appointment_time',
            'notes',
        ]
        widgets = {
            'owner_name': forms.TextInput(attrs={'placeholder': ' '}),
            'owner_email': forms.EmailInput(attrs={'placeholder': ' '}),
            'owner_phone': forms.TextInput(attrs={
                'placeholder': ' ',
                'inputmode': 'numeric',
                'pattern': '[0-9]{11}',
                'minlength': '11',
                'maxlength': '11',
                'oninput': "this.value=this.value.replace(/\\D/g,'')",
            }),
            'owner_address': forms.Textarea(attrs={'rows': 2, 'placeholder': ' '}),
            'pet_name': forms.TextInput(attrs={'placeholder': ' ', 'list': 'petNames', 'oninput': 'if(this.value.length === 1) this.value = this.value.toUpperCase(); else if(this.value.length > 0) this.value = this.value.charAt(0).toUpperCase() + this.value.slice(1);'}),
            'pet_species': forms.TextInput(attrs={'placeholder': ' ', 'oninput': 'if(this.value.length === 1) this.value = this.value.toUpperCase(); else if(this.value.length > 0) this.value = this.value.charAt(0).toUpperCase() + this.value.slice(1);'}),
            'pet_breed': forms.TextInput(attrs={'placeholder': ' ', 'oninput': 'if(this.value.length === 1) this.value = this.value.toUpperCase(); else if(this.value.length > 0) this.value = this.value.charAt(0).toUpperCase() + this.value.slice(1);'}),
            'pet_dob': forms.DateInput(attrs={'type': 'date'}),
            'pet_sex': forms.Select(choices=PET_SEX_CHOICES),
            'pet_color': forms.TextInput(attrs={'placeholder': ' ', 'oninput': 'if(this.value.length === 1) this.value = this.value.toUpperCase(); else if(this.value.length > 0) this.value = this.value.charAt(0).toUpperCase() + this.value.slice(1);'}),
            'pet_symptoms': forms.Textarea(attrs={'rows': 2, 'placeholder': ' '}),
            # reason widget is defined in the field declaration above
            'branch': forms.Select(),
            'preferred_vet': forms.Select(),
            'appointment_date': forms.DateInput(attrs={'type': 'date'}),
            'appointment_time': forms.Select(choices=[('', '-- Select a time slot --')]),
            'notes': forms.Textarea(attrs={'rows': 2, 'placeholder': ' ', 'oninput': 'if(this.value.length === 1) this.value = this.value.toUpperCase(); else if(this.value.length > 0) this.value = this.value.charAt(0).toUpperCase() + this.value.slice(1);'}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        self.fields['branch'].queryset = Branch.objects.filter(is_active=True)
        self.fields['preferred_vet'].queryset = StaffMember.objects.none()
        self.fields['preferred_vet'].required = False
        self.fields['preferred_vet'].empty_label = '-- Any Available Vet --'
        self.fields['pet_species'].required = False
        self.fields['pet_breed'].required = False
        self.fields['pet_dob'].required = False
        self.fields['pet_sex'].required = False
        self.fields['pet_color'].required = False
        self.fields['pet_symptoms'].required = False
        self.fields['owner_email'].required = False
        self.fields['owner_phone'].required = False
        self.fields['owner_address'].required = False
        self.fields['notes'].required = False

        # Set up reason with dynamic choices (mapped to reason_for_visit backend)
        from settings.models import ReasonForVisit
        self.fields['reason'].queryset = ReasonForVisit.objects.filter(is_active=True).order_by('order', 'name')
        self.fields['reason'].label = 'Reason for Visit'

        if self.user:
            self.fields['owner_name'].initial = self.user.get_full_name(
            ) or self.user.username
            self.fields['owner_email'].initial = self.user.email
            self.fields['owner_phone'].initial = self.user.phone_number
            self.fields['owner_address'].initial = self.user.address
            # Pre-fill user's preferred branch if they have one set
            if self.user.branch and self.user.branch.is_active:
                self.fields['branch'].initial = self.user.branch

        # Schedulable roles: veterinarians and vet assistants
        schedulable_roles = ['veterinarian', 'vet_assistant']

        if 'branch' in self.data:
            try:
                branch_id = int(self.data.get('branch'))
                appt_date = self.data.get('appointment_date')

                # If date is provided, get vets/vet assistants scheduled at this branch on this date
                # This matches the API behavior (api_available_vets)
                if appt_date:
                    scheduled_staff_ids = VetSchedule.objects.filter(
                        branch_id=branch_id,
                        date=appt_date,
                        is_available=True,
                    ).values_list('staff_id', flat=True).distinct()

                    self.fields['preferred_vet'].queryset = StaffMember.objects.filter(
                        id__in=scheduled_staff_ids,
                        user__assigned_role__code__in=schedulable_roles,
                        is_active=True,
                    ).select_related('user', 'user__assigned_role')
                else:
                    # No date - return vets/vet assistants assigned to this branch
                    self.fields['preferred_vet'].queryset = StaffMember.objects.filter(
                        user__assigned_role__code__in=schedulable_roles,
                        is_active=True,
                        branch_id=branch_id,
                    ).select_related('user', 'user__assigned_role')
            except (ValueError, TypeError):
                pass

    def clean(self):
        cleaned_data = super().clean()
        # Handle MORNING/AFTERNOON markers for any available vet mode
        time_str = self.data.get('appointment_time')
        if time_str == 'MORNING':
            cleaned_data['appointment_time'] = time(8, 0)
        elif time_str == 'AFTERNOON':
            cleaned_data['appointment_time'] = time(13, 0)
            
        _check_double_booking(cleaned_data)
        return cleaned_data

    def clean_appointment_time(self):
        """
        Parse time from Select widget.
        Accepts:
        - HH:MM format for specific time slots
        - "MORNING" marker for any available morning slot (defaults to 08:00)
        - "AFTERNOON" marker for any available afternoon slot (defaults to 13:00)
        """
        time_str = self.data.get('appointment_time', '')
        if not time_str:
            raise ValidationError('Please select a time slot.')
        
        # Handle MORNING/AFTERNOON markers for "any available vet" mode
        if time_str == 'MORNING':
            return time(8, 0)  # Default morning time, vet will be assigned later
        elif time_str == 'AFTERNOON':
            return time(13, 0)  # Default afternoon time, vet will be assigned later
        
        try:
            hours, minutes = map(int, time_str.split(':'))
            return time(hours, minutes)
        except (ValueError, AttributeError):
            raise ValidationError('Invalid time format. Please select a valid time slot.')

    def clean_appointment_date(self):
        """Validate appointment date is not in the past."""
        appt_date = self.cleaned_data.get('appointment_date')
        if appt_date:
            _validate_appointment_date(appt_date)
        return appt_date

    def clean_owner_phone(self):
        return validate_philippines_phone(self.cleaned_data.get('owner_phone', ''))

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.source = Appointment.Source.PORTAL
        instance.is_returning_customer = True  # Always True for logged-in users

        # Map the 'reason' field (ModelChoiceField) to 'reason_for_visit' ForeignKey
        if 'reason' in self.cleaned_data:
            reason_obj = self.cleaned_data['reason']
            instance.reason_for_visit = reason_obj
        
        if self.user:
            instance.user = self.user
            # Use form values if provided, otherwise fall back to user account values
            if not instance.owner_email:
                instance.owner_email = self.user.email
            if not instance.owner_address:
                instance.owner_address = self.user.address

        # If the user selected an existing registered pet, link it directly
        selected_pet_id = self.cleaned_data.get('selected_pet_id')
        if selected_pet_id:
            from patients.models import Pet
            try:
                instance.pet = Pet.objects.get(pk=selected_pet_id, owner=self.user)
            except Pet.DoesNotExist:
                pass

        # Do not auto-assign vet if none was selected to preserve ANY VET option

        if commit:
            instance.save()
            # Auto-create / link a Patient record for any unlinked pet
            from .utils import sync_pet_from_appointment
            sync_pet_from_appointment(instance)
        return instance


class AdminQuickCreateForm(FormControlMixin, forms.ModelForm):
    """Quick create form for admins — bypasses user restrictions."""

    # Hidden field for selected user ID (for portal bookings)
    selected_user_id = forms.IntegerField(required=False, widget=forms.HiddenInput())
    selected_pet_id = forms.IntegerField(required=False, widget=forms.HiddenInput())
    
    # Use CharField to intercept "MORNING"/"AFTERNOON" text before TimeField validation
    appointment_time = forms.CharField(
        widget=forms.Select(choices=[('', '-- Select a time slot --')]),
        required=True,
    )

    # Explicitly declare reason as ModelChoiceField to work with ReasonForVisit ForeignKey
    reason = forms.ModelChoiceField(
        queryset=None,  # Will be set in __init__
        required=True,
        empty_label='-- Select Reason --',
        widget=forms.Select()
    )

    class Meta:
        """Form metadata."""
        model = Appointment
        fields = [
            'owner_name', 'owner_email', 'owner_phone', 'owner_address',
            'pet_name', 'pet_species', 'pet_breed', 'pet_dob', 'pet_sex', 'pet_color',
            'branch', 'preferred_vet',
            'appointment_date', 'appointment_time',
            'status', 'source', 'notes',
        ]
        widgets = {
            'owner_name': forms.TextInput(attrs={'placeholder': 'Owner name'}),
            'owner_email': forms.EmailInput(attrs={'placeholder': 'email@example.com'}),
            'owner_phone': forms.TextInput(attrs={
                'placeholder': '09XXXXXXXXX',
                'inputmode': 'numeric',
                'pattern': '[0-9]{11}',
                'minlength': '11',
                'maxlength': '11',
                'oninput': "this.value=this.value.replace(/\\D/g,'')",
            }),
            'owner_address': forms.Textarea(attrs={
                'rows': 2, 'placeholder': 'Full address',
            }),
            'pet_name': forms.TextInput(attrs={'placeholder': "Pet's name", 'oninput': 'if(this.value.length === 1) this.value = this.value.toUpperCase(); else if(this.value.length > 0) this.value = this.value.charAt(0).toUpperCase() + this.value.slice(1);'}),
            'pet_species': forms.TextInput(attrs={'placeholder': 'e.g. Dog, Cat', 'oninput': 'if(this.value.length === 1) this.value = this.value.toUpperCase(); else if(this.value.length > 0) this.value = this.value.charAt(0).toUpperCase() + this.value.slice(1);'}),
            'pet_breed': forms.TextInput(attrs={'placeholder': 'e.g. Poodle', 'oninput': 'if(this.value.length === 1) this.value = this.value.toUpperCase(); else if(this.value.length > 0) this.value = this.value.charAt(0).toUpperCase() + this.value.slice(1);'}),
            'pet_dob': forms.DateInput(attrs={'type': 'date'}),
            'pet_sex': forms.Select(choices=PET_SEX_CHOICES),
            'pet_color': forms.TextInput(attrs={'placeholder': 'e.g. Brown', 'oninput': 'if(this.value.length === 1) this.value = this.value.toUpperCase(); else if(this.value.length > 0) this.value = this.value.charAt(0).toUpperCase() + this.value.slice(1);'}),
            # reason widget is defined in the field declaration above
            'branch': forms.Select(),
            'preferred_vet': forms.Select(),
            'appointment_date': forms.DateInput(attrs={'type': 'date'}),
            'status': forms.Select(),
            'source': forms.Select(),
            'notes': forms.Textarea(attrs={
                'rows': 2, 'placeholder': 'Walk-in / phone call notes...',
                'oninput': 'if(this.value.length === 1) this.value = this.value.toUpperCase(); else if(this.value.length > 0) this.value = this.value.charAt(0).toUpperCase() + this.value.slice(1);'
            }),
        }

    def clean_owner_phone(self):
        return validate_philippines_phone(self.cleaned_data.get('owner_phone', ''))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Set minimum date to today to prevent past date selection
        today = timezone.localdate().isoformat()
        self.fields['appointment_date'].widget.attrs['min'] = today
        
        # Set default status to CONFIRMED, instead of PENDING
        if 'status' in self.fields and not self.initial.get('status'):
            self.initial['status'] = Appointment.Status.CONFIRMED
        
        self.fields['branch'].queryset = Branch.objects.filter(is_active=True)
        self.fields['preferred_vet'].queryset = StaffMember.objects.filter(
            user__assigned_role__code='veterinarian',
            is_active=True,
        ).select_related('user', 'user__assigned_role')
        self.fields['preferred_vet'].required = False
        self.fields['preferred_vet'].empty_label = '-- Any Available Vet --'
        self.fields['owner_email'].required = False
        self.fields['owner_phone'].required = False
        self.fields['owner_address'].required = False
        self.fields['pet_species'].required = False
        self.fields['pet_breed'].required = False
        self.fields['pet_dob'].required = False
        self.fields['pet_sex'].required = False
        self.fields['pet_color'].required = False
        self.fields['notes'].required = False
        
        # Set up reason with dynamic choices (mapped to reason_for_visit backend)
        from settings.models import ReasonForVisit
        self.fields['reason'].queryset = ReasonForVisit.objects.filter(is_active=True).order_by('order', 'name')
        self.fields['reason'].label = 'Reason for Visit'
        # empty_label is already set in field declaration

    def clean_appointment_time(self):
        """
        Validate appointment time strictly.
        Supports both:
        - Specific time format (HH:MM or HH:MM:SS)
        - "MORNING" marker for any available morning slot (defaults to 08:00)
        - "AFTERNOON" marker for any available afternoon slot (defaults to 13:00)
        """
        time_str = self.data.get('appointment_time')

        if not time_str:
            raise forms.ValidationError("Appointment time is required.")

        if time_str == 'MORNING':
            return time(8, 0)
        elif time_str == 'AFTERNOON':
            return time(13, 0)

        try:
            parts = time_str.split(':')
            return time(int(parts[0]), int(parts[1]))
        except (ValueError, IndexError):
            raise forms.ValidationError("Please provide a valid time format.")

    def clean(self):
        cleaned_data = super().clean()
        
        # Handle MORNING/AFTERNOON markers for "any available vet" mode
        time_str = self.data.get('appointment_time')
        if time_str == 'MORNING':
            cleaned_data['appointment_time'] = time(8, 0)
            self.cleaned_data['appointment_time'] = time(8, 0)
        elif time_str == 'AFTERNOON':
            cleaned_data['appointment_time'] = time(13, 0)
            self.cleaned_data['appointment_time'] = time(13, 0)
            
        _check_double_booking(cleaned_data)
        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)

        # Map the 'reason' field (ModelChoiceField) to 'reason_for_visit' ForeignKey
        if 'reason' in self.cleaned_data:
            reason_obj = self.cleaned_data['reason']
            instance.reason_for_visit = reason_obj
        
        # Link user if portal source and user_id provided
        user_id = self.cleaned_data.get('selected_user_id')
        if user_id:
            from accounts.models import User
            try:
                instance.user = User.objects.get(pk=user_id)
            except User.DoesNotExist:
                pass

        # If an existing pet was explicitly selected, link it directly
        selected_pet_id = self.cleaned_data.get('selected_pet_id')
        if selected_pet_id:
            from patients.models import Pet
            try:
                instance.pet = Pet.objects.get(pk=selected_pet_id)
            except Pet.DoesNotExist:
                pass

        if commit:
            instance.save()
            # Auto-create / link a Patient record for any unlinked pet info
            from .utils import sync_pet_from_appointment
            sync_pet_from_appointment(instance)
        return instance


class AppointmentEditForm(FormControlMixin, forms.ModelForm):
    """Form for editing existing appointments in admin portal."""
    
    # Use CharField to intercept "MORNING"/"AFTERNOON" text before TimeField validation
    appointment_time = forms.CharField(
        widget=forms.Select(choices=[('', '-- Select a time slot --')]),
        required=True,
    )

    # Explicitly declare reason as ModelChoiceField to work with ReasonForVisit ForeignKey
    reason = forms.ModelChoiceField(
        queryset=None,  # Will be set in __init__
        required=True,
        empty_label='-- Select Reason --',
        widget=forms.Select()
    )

    class Meta:
        """Form metadata."""
        model = Appointment
        fields = [
            'owner_name', 'owner_email', 'owner_phone', 'owner_address',
            'pet_name', 'pet_species', 'pet_breed', 'pet_dob', 'pet_sex', 'pet_color',
            'pet_symptoms',
            'branch', 'preferred_vet',
            'appointment_date', 'appointment_time',
            'status', 'source', 'notes',
        ]
        widgets = {
            'owner_name': forms.TextInput(attrs={'placeholder': 'Owner name'}),
            'owner_email': forms.EmailInput(attrs={'placeholder': 'email@example.com'}),
            'owner_phone': forms.TextInput(attrs={
                'placeholder': '09XXXXXXXXX',
                'inputmode': 'numeric',
                'pattern': '[0-9]{11}',
                'minlength': '11',
                'maxlength': '11',
                'oninput': "this.value=this.value.replace(/\\D/g,'')",
            }),
            'owner_address': forms.Textarea(attrs={
                'rows': 2, 'placeholder': 'Full address',
            }),
            'pet_name': forms.TextInput(attrs={'placeholder': "Pet's name", 'oninput': 'if(this.value.length === 1) this.value = this.value.toUpperCase(); else if(this.value.length > 0) this.value = this.value.charAt(0).toUpperCase() + this.value.slice(1);'}),
            'pet_species': forms.TextInput(attrs={'placeholder': 'e.g. Dog, Cat', 'oninput': 'if(this.value.length === 1) this.value = this.value.toUpperCase(); else if(this.value.length > 0) this.value = this.value.charAt(0).toUpperCase() + this.value.slice(1);'}),
            'pet_breed': forms.TextInput(attrs={'placeholder': 'e.g. Poodle', 'oninput': 'if(this.value.length === 1) this.value = this.value.toUpperCase(); else if(this.value.length > 0) this.value = this.value.charAt(0).toUpperCase() + this.value.slice(1);'}),
            'pet_dob': forms.DateInput(attrs={'type': 'date'}),
            'pet_sex': forms.Select(choices=PET_SEX_CHOICES),
            'pet_color': forms.TextInput(attrs={'placeholder': 'e.g. Brown', 'oninput': 'if(this.value.length === 1) this.value = this.value.toUpperCase(); else if(this.value.length > 0) this.value = this.value.charAt(0).toUpperCase() + this.value.slice(1);'}),
            'pet_symptoms': forms.Textarea(attrs={
                'rows': 2, 'placeholder': 'Current symptoms',
            }),
            # reason widget is defined in the field declaration above
            'branch': forms.Select(),
            'preferred_vet': forms.Select(),
            'appointment_date': forms.DateInput(attrs={'type': 'date'}),
            'status': forms.Select(),
            'source': forms.Select(),
            'notes': forms.Textarea(attrs={
                'rows': 2, 'placeholder': 'Additional notes...',
                'oninput': 'if(this.value.length === 1) this.value = this.value.toUpperCase(); else if(this.value.length > 0) this.value = this.value.charAt(0).toUpperCase() + this.value.slice(1);'
            }),
        }

    def clean_owner_phone(self):
        return validate_philippines_phone(self.cleaned_data.get('owner_phone', ''))

    def clean_appointment_time(self):
        """
        Validate appointment time strictly.
        Supports both:
        - Specific time format (HH:MM or HH:MM:SS)
        - "MORNING" marker for any available morning slot (defaults to 08:00)
        - "AFTERNOON" marker for any available afternoon slot (defaults to 13:00)
        """
        time_str = self.data.get('appointment_time')

        if not time_str:
            raise forms.ValidationError("Appointment time is required.")

        if time_str == 'MORNING':
            return time(8, 0)
        elif time_str == 'AFTERNOON':
            return time(13, 0)

        try:
            parts = time_str.split(':')
            return time(int(parts[0]), int(parts[1]))
        except (ValueError, IndexError):
            raise forms.ValidationError("Please provide a valid time format.")

    def clean(self):
        """Validate appointment edit form - allow past dates for editing historical appointments."""
        cleaned_data = super().clean()
        
        # Handle MORNING/AFTERNOON markers for "any available vet" mode
        time_str = self.data.get('appointment_time')
        if time_str == 'MORNING':
            cleaned_data['appointment_time'] = time(8, 0)
            self.cleaned_data['appointment_time'] = time(8, 0)
        elif time_str == 'AFTERNOON':
            cleaned_data['appointment_time'] = time(13, 0)
            self.cleaned_data['appointment_time'] = time(13, 0)
            
        instance_id = self.instance.pk if self.instance else None
        _check_double_booking(cleaned_data, allow_past=True, instance_id=instance_id)
        return cleaned_data

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Set minimum date to today to prevent past date selection
        today = timezone.localdate().isoformat()
        self.fields['appointment_date'].widget.attrs['min'] = today
        
        self.fields['branch'].queryset = Branch.objects.filter(is_active=True)
        
        # For edit form: include all active vets so they can always be selected
        # Even if they're not scheduled on the new date
        self.fields['preferred_vet'].queryset = StaffMember.objects.filter(
            user__assigned_role__code='veterinarian',
            is_active=True,
        ).select_related('user', 'user__assigned_role')
        
        self.fields['preferred_vet'].required = False
        self.fields['preferred_vet'].empty_label = '-- Any Available Vet --'
        self.fields['owner_email'].required = False
        self.fields['owner_phone'].required = False
        self.fields['owner_address'].required = False
        self.fields['pet_species'].required = False
        self.fields['pet_breed'].required = False
        self.fields['pet_dob'].required = False
        self.fields['pet_sex'].required = False
        self.fields['pet_color'].required = False
        self.fields['pet_symptoms'].required = False
        self.fields['notes'].required = False
        
        # Set up reason with dynamic choices (mapped to reason_for_visit backend)
        from settings.models import ReasonForVisit
        self.fields['reason'].queryset = ReasonForVisit.objects.all().order_by('order', 'name')
        self.fields['reason'].label = 'Reason for Visit'
        # empty_label is already set in field declaration
        
        # Set initial value from reason_for_visit ForeignKey when editing
        if self.instance and self.instance.pk and self.instance.reason_for_visit:
            self.fields['reason'].initial = self.instance.reason_for_visit
    
    def save(self, commit=True):
        """Override save to map 'reason' field to 'reason_for_visit' ForeignKey."""
        instance = super().save(commit=False)

        # Map the 'reason' field (ModelChoiceField) to 'reason_for_visit' ForeignKey
        if 'reason' in self.cleaned_data:
            reason_obj = self.cleaned_data['reason']
            instance.reason_for_visit = reason_obj
        
        if commit:
            instance.save()
        return instance
