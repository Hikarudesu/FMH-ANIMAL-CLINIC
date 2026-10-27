"""
Forms for the appointments app.
"""
# pylint: disable=no-member


from datetime import time, date, datetime, timedelta
from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils import timezone
from FMHANIMALCLINIC.form_mixins import FormControlMixin, validate_philippines_phone

from branches.models import Branch
from employees.models import StaffMember, VetSchedule
from settings.utils import get_setting

from .models import Appointment
from .clinic_hours import CLINIC_CLOSE_TIME, CLINIC_OPEN_TIME
from .services import AppointmentService
from accounts.owner_identity import check_existing_owner_identity


PET_SEX_CHOICES = [
    ('', '---'),
    ('MALE', 'Male'),
    ('FEMALE', 'Female'),
]

PORTAL_DUPLICATE_PET_NAME_ERROR = (
    'This pet name is already registered to your account. '
    'Select the existing pet above, or enter a different name.'
)
GUEST_DUPLICATE_PET_NAME_ERROR = (
    'A pet with this name is already registered under these owner details. '
    'Please check the pet name or contact the clinic if this is a different pet.'
)
def _guest_pet_name_exists(
    name,
    owner_name,
    owner_email='',
    owner_phone='',
    exclude_pet_id=None,
):
    """Check for a walk-in pet with the same name and matching guest identity."""
    from patients.models import Pet

    pets = Pet.objects.filter(
        source=Pet.Source.WALKIN,
        name__iexact=name,
        guest_owner_name__iexact=owner_name,
    )
    if exclude_pet_id:
        pets = pets.exclude(pk=exclude_pet_id)
    contact_match = Q()
    if owner_email:
        contact_match |= Q(guest_owner_email__iexact=owner_email)
    if owner_phone:
        contact_match |= Q(guest_owner_phone=owner_phone)

    return pets.filter(contact_match).exists() if contact_match else pets.exists()


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

    try:
        max_advance_days = max(1, int(get_setting('appointment_max_advance_days', 180)))
    except (TypeError, ValueError):
        max_advance_days = 180
    if appt_date > today + timedelta(days=max_advance_days):
        raise ValidationError(
            f'Appointment date cannot be more than {max_advance_days} days in advance.'
        )


def _validate_vet_schedule(branch, appt_date, vet=None):
    """Validate that there are vets scheduled at the branch on the date."""
    if not branch or not appt_date:
        return

    # Only consider veterinarians and vet assistants for appointment bookings
    schedulable_roles = ['veterinarian', 'assistant_veterinarian']

    # Check if there are any scheduled vets for this branch and date
    scheduled_vet_ids = list(VetSchedule.objects.filter(
        branch=branch,
        date=appt_date,
        is_available=True,
        staff__is_active=True,
        staff__user__is_active=True,
        staff__user__assigned_role__code__in=schedulable_roles,
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

    slot_end = (
        datetime.combine(appt_date, appt_time)
        + timedelta(minutes=AppointmentService.SLOT_DURATION_MINUTES)
    ).time()
    if appt_time < CLINIC_OPEN_TIME or slot_end > CLINIC_CLOSE_TIME:
        raise ValidationError(
            'Appointments must be scheduled between 8:00 AM and 7:00 PM.'
        )

    # Validate appointment date is not in the past (skip for admin editing)
    _validate_appointment_date(appt_date, allow_past=allow_past)
    if (
        not allow_past
        and appt_date == timezone.localdate()
        and appt_time <= timezone.localtime().time()
    ):
        raise ValidationError(
            'This appointment time has already passed. '
            'Please select a future time slot.'
        )

    # Validate vets are scheduled at this branch on this date
    _validate_vet_schedule(branch, appt_date, vet)

    if time(12, 0) <= appt_time < time(13, 0):
        raise ValidationError(
            'Appointments cannot be scheduled between 12:00 PM and 1:00 PM (Lunch Break).'
        )

    available_slots = AppointmentService.get_available_slots(
        vet_id=vet.pk if vet else None,
        target_date=appt_date,
        branch_id=branch.pk,
        exclude_appointment_id=instance_id,
        include_elapsed_slots=allow_past,
    )
    requested_slot = appt_time.strftime('%H:%M')
    if not any(
        slot['time'] == requested_slot and slot['available']
        for slot in available_slots
    ):
        if vet:
            raise ValidationError(
                'This time slot is already booked for this veterinarian. '
                'Please select a different time.'
            )
        raise ValidationError(
            'All veterinarians are fully booked at this time. '
            'Please select a different time slot.'
        )


def _resolve_flexible_appointment_time(
    cleaned_data,
    requested_period,
    instance_id=None,
    allow_past=False,
):
    """Resolve a Morning/Afternoon choice to an actually available slot."""
    if requested_period not in ('MORNING', 'AFTERNOON'):
        return

    branch = cleaned_data.get('branch')
    appt_date = cleaned_data.get('appointment_date')
    if not branch or not appt_date:
        return

    vet = cleaned_data.get('preferred_vet')
    slots = AppointmentService.get_available_slots(
        vet_id=vet.pk if vet else None,
        target_date=appt_date,
        branch_id=branch.pk,
        exclude_appointment_id=instance_id,
        include_elapsed_slots=allow_past,
    )
    for slot in slots:
        if not slot['available']:
            continue
        slot_time = time.fromisoformat(slot['time'])
        if (
            requested_period == 'MORNING' and slot_time < time(12, 0)
        ) or (
            requested_period == 'AFTERNOON' and slot_time >= time(13, 0)
        ):
            cleaned_data['appointment_time'] = slot_time
            return

    period_label = 'morning' if requested_period == 'MORNING' else 'afternoon'
    raise ValidationError(
        f'No available {period_label} appointment times remain. '
        'Please select another time period or date.'
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
            'appointment_date': forms.DateInput(attrs={
                'type': 'date',
                'placeholder': 'Select appointment date',
                'title': 'Select an appointment date',
                'aria-label': 'Select an appointment date',
            }),
            'appointment_time': forms.Select(choices=[('', '-- Select a time slot --')]),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['branch'].queryset = Branch.objects.filter(is_active=True)
        self.fields['preferred_vet'].queryset = StaffMember.objects.none()
        self.fields['preferred_vet'].required = False
        self.fields['preferred_vet'].empty_label = (
            '-- No preference (unassigned until consultation) --'
        )
        self.fields['pet_species'].required = True
        self.fields['pet_breed'].required = False
        self.fields['pet_dob'].required = False
        self.fields['pet_sex'].required = True
        self.fields['pet_color'].required = False
        self.fields['pet_symptoms'].required = False
        self.fields['owner_email'].required = True
        self.fields['owner_phone'].required = True
        self.fields['owner_address'].required = False
        
        # Set up reason with dynamic choices (mapped to reason_for_visit backend)
        from settings.models import ReasonForVisit
        self.fields['reason'].queryset = ReasonForVisit.objects.filter(is_active=True).order_by('order', 'name')
        self.fields['reason'].label = 'Reason for Visit'
        # empty_label is already set in field declaration

        # Schedulable roles: veterinarians and vet assistants
        schedulable_roles = ['veterinarian', 'assistant_veterinarian']

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
                        user__is_active=True,
                        is_active=True,
                    ).select_related('user', 'user__assigned_role')
                else:
                    # No date - return vets/vet assistants assigned to this branch
                    self.fields['preferred_vet'].queryset = StaffMember.objects.filter(
                        user__assigned_role__code__in=schedulable_roles,
                        user__is_active=True,
                        is_active=True,
                        branch_id=branch_id,
                    ).select_related('user', 'user__assigned_role')
            except (ValueError, TypeError):
                pass

    def clean(self):
        cleaned_data = super().clean()

        pet_name = (cleaned_data.get('pet_name') or '').strip()
        owner_name = (cleaned_data.get('owner_name') or '').strip()
        if pet_name and owner_name and _guest_pet_name_exists(
            pet_name,
            owner_name,
            (cleaned_data.get('owner_email') or '').strip(),
            (cleaned_data.get('owner_phone') or '').strip(),
        ):
            self.add_error('pet_name', GUEST_DUPLICATE_PET_NAME_ERROR)

        _resolve_flexible_appointment_time(
            cleaned_data,
            self.data.get('appointment_time'),
        )
        _check_double_booking(cleaned_data)
        return cleaned_data

    def clean_appointment_time(self):
        """
        Parse time from Select widget.
        Accepts:
        - HH:MM format for specific time slots
        - "MORNING" and "AFTERNOON" markers resolved to an available slot
        """
        time_str = self.data.get('appointment_time', '')
        if not time_str:
            raise ValidationError('Please select a time slot.')
        
        # The form's clean() resolves these markers to an available slot.
        if time_str == 'MORNING':
            return time(8, 0)
        elif time_str == 'AFTERNOON':
            return time(13, 0)
        
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
            'appointment_date': forms.DateInput(attrs={
                'type': 'date',
                'placeholder': ' ',
                'title': 'Select an appointment date',
                'aria-label': 'Select an appointment date',
            }),
            'appointment_time': forms.Select(choices=[('', '-- Select a time slot --')]),
            'notes': forms.Textarea(attrs={'rows': 2, 'placeholder': ' ', 'oninput': 'if(this.value.length === 1) this.value = this.value.toUpperCase(); else if(this.value.length > 0) this.value = this.value.charAt(0).toUpperCase() + this.value.slice(1);'}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        selected_pet = kwargs.pop('selected_pet', None)
        super().__init__(*args, **kwargs)
        self.fields['branch'].queryset = Branch.objects.filter(is_active=True)
        self.fields['preferred_vet'].queryset = StaffMember.objects.none()
        self.fields['preferred_vet'].required = False
        self.fields['preferred_vet'].empty_label = (
            '-- No preference (unassigned until consultation) --'
        )
        self.fields['pet_species'].required = True
        self.fields['pet_breed'].required = False
        self.fields['pet_dob'].required = False
        self.fields['pet_sex'].required = True
        self.fields['pet_color'].required = False
        self.fields['pet_symptoms'].required = False
        self.fields['owner_email'].required = True
        self.fields['owner_phone'].required = True
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

        if selected_pet is not None and (
            self.user is None or selected_pet.owner_id == self.user.pk
        ):
            self.initial.update({
                'selected_pet_id': selected_pet.pk,
                'pet_name': selected_pet.name,
                'pet_species': selected_pet.species,
                'pet_breed': selected_pet.breed,
                'pet_dob': selected_pet.date_of_birth,
                'pet_sex': selected_pet.sex,
                'pet_color': selected_pet.color,
            })

        # Schedulable roles: veterinarians and vet assistants
        schedulable_roles = ['veterinarian', 'assistant_veterinarian']

        branch_value = (
            self.data.get('branch')
            or self.initial.get('branch')
            or self.fields['branch'].initial
        )
        if branch_value:
            try:
                branch_id = int(getattr(branch_value, 'pk', branch_value))
                source_vet_id = self.initial.get('followup_source_vet_id')
                appt_date = (
                    self.data.get('appointment_date')
                    or self.initial.get('appointment_date')
                )

                # If date is provided, get vets/vet assistants scheduled at this branch on this date
                # This matches the API behavior (api_available_vets)
                if appt_date:
                    scheduled_staff_ids = VetSchedule.objects.filter(
                        branch_id=branch_id,
                        date=appt_date,
                        is_available=True,
                    ).values_list('staff_id', flat=True).distinct()

                    vet_filter = Q(id__in=scheduled_staff_ids)
                    if source_vet_id:
                        vet_filter |= Q(
                            pk=source_vet_id,
                            branch_id=branch_id,
                        )
                    self.fields['preferred_vet'].queryset = StaffMember.objects.filter(
                        vet_filter,
                        user__assigned_role__code__in=schedulable_roles,
                        user__is_active=True,
                        is_active=True,
                    ).select_related('user', 'user__assigned_role')
                else:
                    # No date - return vets/vet assistants assigned to this branch
                    self.fields['preferred_vet'].queryset = StaffMember.objects.filter(
                        user__assigned_role__code__in=schedulable_roles,
                        user__is_active=True,
                        is_active=True,
                        branch_id=branch_id,
                    ).select_related('user', 'user__assigned_role')
                if source_vet_id:
                    self.fields['preferred_vet'].widget.attrs[
                        'data-followup-prefill-vet'
                    ] = str(source_vet_id)
                    self.fields['preferred_vet'].widget.attrs[
                        'data-followup-prefill-branch'
                    ] = str(branch_id)
            except (ValueError, TypeError):
                pass

    def clean(self):
        cleaned_data = super().clean()
        from accounts.models import User

        owner_name = ' '.join((cleaned_data.get('owner_name') or '').split())
        if self.user and owner_name:
            name_parts = owner_name.split(maxsplit=1)
            if any(
                len(part) > User._meta.get_field(field_name).max_length
                for part, field_name in zip(
                    name_parts,
                    ('first_name', 'last_name'),
                )
            ):
                self.add_error(
                    'owner_name',
                    'Owner name is too long to save to your profile. '
                    'Please shorten the first or last name.',
                )
        email = (cleaned_data.get('owner_email') or '').strip()
        if (
            self.user
            and email.casefold() != (self.user.email or '').strip().casefold()
            and check_existing_owner_identity(
                '',
                email=email,
                exclude_user_id=self.user.pk,
            )['email_match']
        ):
            self.add_error(
                'owner_email',
                'This email is already linked to another registered account or '
                'guest owner record. Enter an email address that is not in use '
                'so the appointment stays associated with the correct owner.',
            )
        _resolve_flexible_appointment_time(
            cleaned_data,
            self.data.get('appointment_time'),
        )
        _check_double_booking(cleaned_data)
        return cleaned_data

    def clean_appointment_time(self):
        """
        Parse time from Select widget.
        Accepts:
        - HH:MM format for specific time slots
        - "MORNING" and "AFTERNOON" markers resolved to an available slot
        """
        time_str = self.data.get('appointment_time', '')
        if not time_str:
            raise ValidationError('Please select a time slot.')
        
        # The form's clean() resolves these markers to an available slot.
        if time_str == 'MORNING':
            return time(8, 0)
        elif time_str == 'AFTERNOON':
            return time(13, 0)
        
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

    def clean_pet_name(self):
        name = self.cleaned_data['pet_name'].strip()
        if not self.user:
            return name

        from patients.models import Pet

        duplicate_pets = Pet.objects.filter(
            owner=self.user,
            name__iexact=name,
        )
        try:
            selected_pet_id = int(self.data.get('selected_pet_id', ''))
        except (TypeError, ValueError):
            selected_pet_id = None
        if selected_pet_id:
            duplicate_pets = duplicate_pets.exclude(pk=selected_pet_id)
        if duplicate_pets.exists():
            raise ValidationError(PORTAL_DUPLICATE_PET_NAME_ERROR)
        return name

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.source = Appointment.Source.PORTAL
        instance.is_returning_customer = True  # Always True for logged-in users
        instance.owner_name = ' '.join(
            (self.cleaned_data.get('owner_name') or '').split()
        )

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
            if self.user:
                owner_name = ' '.join(
                    (self.cleaned_data.get('owner_name') or '').split()
                )
                name_parts = owner_name.split(maxsplit=1)
                profile_updates = {
                    'first_name': name_parts[0] if name_parts else '',
                    'last_name': name_parts[1] if len(name_parts) > 1 else '',
                    'email': instance.owner_email,
                    'phone_number': instance.owner_phone,
                    'address': instance.owner_address,
                }
                original_email = self.user.email or ''
                update_fields = []
                for field_name, value in profile_updates.items():
                    if getattr(self.user, field_name) != value:
                        setattr(self.user, field_name, value)
                        update_fields.append(field_name)
                if (
                    'email' in update_fields
                    and self.user.email.strip().casefold()
                    != original_email.strip().casefold()
                ):
                    self.user.email_verified = False
                    update_fields.append('email_verified')
                if update_fields:
                    self.user.save(update_fields=update_fields)
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
            'owner_email': forms.EmailInput(attrs={
                'placeholder': 'email@example.com',
                'readonly': 'readonly',
            }),
            'owner_phone': forms.TextInput(attrs={
                'placeholder': '09XXXXXXXXX',
                'inputmode': 'numeric',
                'pattern': '[0-9]{11}',
                'minlength': '11',
                'maxlength': '11',
                'oninput': "this.value=this.value.replace(/\\D/g,'')",
                'readonly': 'readonly',
            }),
            'owner_address': forms.Textarea(attrs={
                'rows': 2,
                'placeholder': 'Full address',
                'readonly': 'readonly',
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
            'appointment_date': forms.DateInput(attrs={
                'type': 'date',
                'placeholder': 'Select appointment date',
                'title': 'Select an appointment date',
                'aria-label': 'Select an appointment date',
            }),
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
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        # Set minimum date to today to prevent past date selection
        today = timezone.localdate().isoformat()
        self.fields['appointment_date'].widget.attrs['min'] = today
        
        # Set default status to CONFIRMED, instead of PENDING
        if 'status' in self.fields:
            if not self.initial.get('status'):
                self.initial['status'] = Appointment.Status.CONFIRMED
            # Prioritize CONFIRMED in the choices dropdown
            self.fields['status'].choices = [
                (Appointment.Status.CONFIRMED, 'Confirmed'),
                (Appointment.Status.PENDING, 'Pending'),
                (Appointment.Status.CHECKED_IN, 'Checked In — Walk-in arrived'),
            ]
        
        self.fields['branch'].queryset = Branch.objects.filter(is_active=True)
        
        # Filter vets based on user's branch restriction
        vets_query = StaffMember.objects.filter(
            user__assigned_role__code__in=['veterinarian', 'assistant_veterinarian'],
            user__is_active=True,
            is_active=True,
        )
        
        # For an unselected branch, keep branch-restricted users scoped to
        # their home branch. When a branch is explicitly selected, the
        # schedule query below determines which vets may be selected there.
        if (
            self.user
            and self.user.is_module_branch_restricted('appointments')
            and self.user.branch
            and not self.data.get('branch')
        ):
            vets_query = vets_query.filter(branch=self.user.branch)

        selected_branch_id = self.data.get('branch')
        selected_date = self.data.get('appointment_date')
        if selected_branch_id and selected_date:
            scheduled_staff_ids = VetSchedule.objects.filter(
                branch_id=selected_branch_id,
                date=selected_date,
                is_available=True,
                staff__user__assigned_role__code__in=[
                    'veterinarian', 'assistant_veterinarian'
                ],
            ).values_list('staff_id', flat=True).distinct()
            vets_query = vets_query.filter(id__in=scheduled_staff_ids)

        selected_vet_id = self.data.get('preferred_vet')
        if selected_vet_id:
            selected_vet = StaffMember.objects.filter(
                pk=selected_vet_id,
                user__assigned_role__code__in=[
                    'veterinarian', 'assistant_veterinarian'
                ],
                user__is_active=True,
                is_active=True,
            ).first()
            scheduled_for_selection = bool(
                selected_vet
                and selected_branch_id
                and selected_date
                and VetSchedule.objects.filter(
                    staff=selected_vet,
                    branch_id=selected_branch_id,
                    date=selected_date,
                    is_available=True,
                ).exists()
            )
            branch_allowed = bool(
                selected_vet
                and (
                    not self.user
                    or not self.user.is_module_branch_restricted('appointments')
                    or not self.user.branch
                    or selected_vet.branch_id == self.user.branch_id
                    or scheduled_for_selection
                )
            )
            if selected_vet and branch_allowed and not vets_query.filter(
                pk=selected_vet.pk
            ).exists():
                vets_query = vets_query | StaffMember.objects.filter(
                    pk=selected_vet.pk
                )
        
        self.fields['preferred_vet'].queryset = vets_query.select_related('user', 'user__assigned_role')
        self.fields['preferred_vet'].required = False
        self.fields['preferred_vet'].empty_label = (
            '-- No preference (unassigned until consultation) --'
        )
        self.fields['owner_email'].required = True
        self.fields['owner_phone'].required = True
        # Portal appointments receive the owner name from the selected account.
        self.fields['owner_name'].required = False
        self.fields['owner_address'].required = False
        self.fields['source'].required = True
        self.fields['pet_species'].required = True
        self.fields['pet_breed'].required = False
        self.fields['pet_dob'].required = False
        self.fields['pet_sex'].required = True
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

        source = cleaned_data.get('source')
        pet_name = (cleaned_data.get('pet_name') or '').strip()
        selected_pet_id = cleaned_data.get('selected_pet_id')

        if source == Appointment.Source.WALKIN and not (
            cleaned_data.get('owner_name') or ''
        ).strip():
            self.add_error('owner_name', 'Owner name is required for walk-in appointments.')
        if source == Appointment.Source.PORTAL:
            from accounts.models import User

            selected_owner = User.objects.filter(
                pk=cleaned_data.get('selected_user_id')
            ).first()
            email = (cleaned_data.get('owner_email') or '').strip()
            if (
                selected_owner
                and email.casefold() != (selected_owner.email or '').strip().casefold()
                and check_existing_owner_identity(
                    '',
                    email=email,
                    exclude_user_id=selected_owner.pk,
                )['email_match']
            ):
                self.add_error(
                    'owner_email',
                    'This email address is already associated with another owner record. '
                    'Enter a different email address.',
                )
            if selected_owner:
                profile_details = {
                    'owner_name': selected_owner.get_full_name() or selected_owner.username,
                    'owner_email': selected_owner.email or '',
                    'owner_phone': selected_owner.phone_number or '',
                    'owner_address': selected_owner.address or '',
                }
                changed_profile_details = any(
                    (
                        (cleaned_data.get(field_name) or '').strip().casefold()
                        != value.strip().casefold()
                        if field_name == 'owner_email'
                        else (cleaned_data.get(field_name) or '').strip()
                        != value.strip()
                    )
                    for field_name, value in profile_details.items()
                )
                if changed_profile_details:
                    self.add_error(
                        None,
                        'Registered client details are read-only here. '
                        'Update the client’s portal profile if a correction is needed.',
                    )
                cleaned_data.update(profile_details)
        if pet_name and source == Appointment.Source.PORTAL:
            from patients.models import Pet

            owner = selected_owner
            if owner:
                existing_pets = Pet.objects.filter(
                    owner=owner,
                    name__iexact=pet_name,
                )
                if selected_pet_id:
                    existing_pets = existing_pets.exclude(pk=selected_pet_id)
                if existing_pets.exists():
                    self.add_error('pet_name', PORTAL_DUPLICATE_PET_NAME_ERROR)
        elif pet_name and source == Appointment.Source.WALKIN:
            if selected_pet_id:
                from patients.models import Pet

                selected_guest_pet = Pet.objects.filter(
                    pk=selected_pet_id,
                    source=Pet.Source.WALKIN,
                    guest_owner_name__iexact=(cleaned_data.get('owner_name') or '').strip(),
                )
                owner_phone = (cleaned_data.get('owner_phone') or '').strip()
                owner_email = (cleaned_data.get('owner_email') or '').strip()
                owner_address = (cleaned_data.get('owner_address') or '').strip()
                if owner_phone:
                    selected_guest_pet = selected_guest_pet.filter(
                        guest_owner_phone=owner_phone,
                    )
                if owner_email:
                    selected_guest_pet = selected_guest_pet.filter(
                        guest_owner_email__iexact=owner_email,
                    )
                if owner_address:
                    selected_guest_pet = selected_guest_pet.filter(
                        guest_owner_address__iexact=owner_address,
                    )
                if not selected_guest_pet.exists():
                    self.add_error(
                        'selected_pet_id',
                        'The selected pet does not belong to the selected guest. '
                        'Choose a pet from the matching owner details.',
                    )
            if _guest_pet_name_exists(
                pet_name,
                (cleaned_data.get('owner_name') or '').strip(),
                (cleaned_data.get('owner_email') or '').strip(),
                (cleaned_data.get('owner_phone') or '').strip(),
                exclude_pet_id=selected_pet_id,
            ):
                self.add_error('pet_name', GUEST_DUPLICATE_PET_NAME_ERROR)

        if source == Appointment.Source.WALKIN and (cleaned_data.get('owner_name') or '').strip():
            from accounts.models import User

            registered_portal_owners = User.objects.filter(
                Q(assigned_role__is_staff_role=False)
                | Q(assigned_role__isnull=True),
                is_staff=False,
                is_superuser=False,
            )
            email = (cleaned_data.get('owner_email') or '').strip()
            if email and registered_portal_owners.filter(
                email__iexact=email,
            ).exists():
                self.add_error(
                    'owner_email',
                    'This email belongs to a registered portal account. '
                    'Use the registered client source or enter a different email address.',
                )

        time_str = self.data.get('appointment_time')
        _resolve_flexible_appointment_time(cleaned_data, time_str)
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
            if (
                instance.status == Appointment.Status.CHECKED_IN
                and not instance.checked_in_at
            ):
                instance.checked_in_at = timezone.now()
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
            'appointment_date': forms.DateInput(attrs={
                'type': 'date',
                'placeholder': 'Select appointment date',
                'title': 'Select an appointment date',
                'aria-label': 'Select an appointment date',
            }),
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

        appointment_date = cleaned_data.get('appointment_date')
        requested_status = self.data.get('status')
        if requested_status and requested_status != self.instance.status:
            self.add_error(
                'status',
                'Use the appointment workflow actions to change appointment status.',
            )
        if (
            requested_status == Appointment.Status.COMPLETED
            and appointment_date
            and appointment_date > timezone.localdate()
        ):
            self.add_error(
                'status',
                'This appointment cannot be marked completed before its scheduled date.',
            )
        
        time_str = self.data.get('appointment_time')
        instance_id = self.instance.pk if self.instance else None
        _resolve_flexible_appointment_time(
            cleaned_data,
            time_str,
            instance_id=instance_id,
            allow_past=True,
        )
        _check_double_booking(cleaned_data, allow_past=True, instance_id=instance_id)
        return cleaned_data

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        self.fields['status'].disabled = True
        # Set minimum date to today to prevent past date selection
        today = timezone.localdate().isoformat()
        self.fields['appointment_date'].widget.attrs['min'] = today
        
        self.fields['branch'].queryset = Branch.objects.filter(is_active=True)
        
        # Filter vets based on user's branch restriction
        vets_query = StaffMember.objects.filter(
            user__assigned_role__code__in=['veterinarian', 'assistant_veterinarian'],
            user__is_active=True,
            is_active=True,
        )
        
        # If user is branch-restricted, only show vets from their branch
        if self.user and self.user.is_module_branch_restricted('appointments') and self.user.branch:
            vets_query = vets_query.filter(branch=self.user.branch)

        # Keep the existing veterinarian valid when editing a historical
        # appointment, even if the vet is no longer in the active queryset.
        if self.instance and self.instance.pk and self.instance.preferred_vet_id:
            current_vet = StaffMember.objects.filter(
                pk=self.instance.preferred_vet_id,
            ).first()
            if current_vet and not vets_query.filter(pk=current_vet.pk).exists():
                vets_query = vets_query | StaffMember.objects.filter(pk=current_vet.pk)
        
        # The availability API can return a vet scheduled at the selected
        # branch even when that vet is assigned to another home branch. Keep
        # that submitted scheduled vet valid for this booking.
        selected_vet_id = self.data.get('preferred_vet')
        selected_branch_id = self.data.get('branch')
        selected_date = self.data.get('appointment_date')
        if selected_vet_id:
            selected_vet = StaffMember.objects.filter(
                pk=selected_vet_id,
                user__assigned_role__code__in=[
                    'veterinarian', 'assistant_veterinarian'
                ],
                user__is_active=True,
                is_active=True,
            ).first()
            scheduled_for_selection = bool(
                selected_vet
                and selected_branch_id
                and selected_date
                and VetSchedule.objects.filter(
                    staff=selected_vet,
                    branch_id=selected_branch_id,
                    date=selected_date,
                    is_available=True,
                ).exists()
            )
            branch_allowed = bool(
                selected_vet
                and (
                    not self.user
                    or not self.user.is_module_branch_restricted('appointments')
                    or not self.user.branch
                    or selected_vet.branch_id == self.user.branch_id
                    or (
                        selected_branch_id == str(self.user.branch_id)
                        and scheduled_for_selection
                    )
                )
            )
            if selected_vet and branch_allowed and not vets_query.filter(
                pk=selected_vet.pk
            ).exists():
                vets_query = vets_query | StaffMember.objects.filter(
                    pk=selected_vet.pk
                )

        self.fields['preferred_vet'].queryset = vets_query.select_related('user', 'user__assigned_role')
        
        self.fields['preferred_vet'].required = False
        self.fields['preferred_vet'].empty_label = (
            '-- No preference (unassigned until consultation) --'
        )
        self.fields['owner_email'].required = True
        self.fields['owner_phone'].required = True
        self.fields['owner_address'].required = False
        self.fields['source'].required = True
        self.fields['pet_species'].required = True
        self.fields['pet_breed'].required = False
        self.fields['pet_dob'].required = False
        self.fields['pet_sex'].required = True
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


class AppointmentCancellationForm(forms.Form):
    """Require an auditable reason when an owner or staff member cancels."""

    cancellation_reason = forms.CharField(
        label='Reason for cancellation',
        min_length=5,
        max_length=2000,
        widget=forms.Textarea(attrs={
            'rows': 3,
            'placeholder': 'Please explain why this appointment is being cancelled.',
        }),
    )
