from django import forms
from .models import StaffMember, VetSchedule, RecurringSchedule
from FMHANIMALCLINIC.form_mixins import FormControlMixin, validate_philippines_phone


class StaffMemberForm(FormControlMixin, forms.ModelForm):
    """Form for creating/editing staff members."""

    class Meta:
        model = StaffMember
        fields = [
            'first_name', 'last_name', 'email', 'phone',
            'position', 'salary', 'branch', 'date_hired',
            'license_number', 'license_expiry', 'is_active',
        ]
        widgets = {
            'first_name': forms.TextInput(attrs={'placeholder': 'First name'}),
            'last_name': forms.TextInput(attrs={'placeholder': 'Last name'}),
            'email': forms.EmailInput(attrs={'placeholder': 'email@example.com'}),
            'phone': forms.TextInput(attrs={
                'placeholder': '09XXXXXXXXX',
                'inputmode': 'numeric',
                'pattern': '[0-9]{11}',
                'minlength': '11',
                'maxlength': '11',
                'oninput': "this.value=this.value.replace(/\\D/g,'')",
            }),
            'salary': forms.NumberInput(attrs={'placeholder': '0.00', 'step': '0.01'}),
            'date_hired': forms.DateInput(attrs={'type': 'date'}),
            'license_number': forms.TextInput(attrs={'placeholder': 'PRC License #'}),
            'license_expiry': forms.DateInput(attrs={'type': 'date'}),
        }

    def clean_phone(self):
        return validate_philippines_phone(self.cleaned_data.get('phone', ''))


class VetScheduleForm(FormControlMixin, forms.ModelForm):
    """Form for creating a schedule entry."""

    class Meta:
        model = VetSchedule
        fields = ['staff', 'date', 'start_time', 'end_time',
                  'branch', 'shift_type', 'is_available', 'notes']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
            'start_time': forms.TimeInput(attrs={'type': 'time'}),
            'end_time': forms.TimeInput(attrs={'type': 'time'}),
            'notes': forms.Textarea(attrs={'rows': 2, 'placeholder': 'Optional notes...'}),
        }

    def __init__(self, *args, is_admin=True, **kwargs):
        super().__init__(*args, **kwargs)
        # Show staff who can be scheduled (using centralized manager method)
        self.fields['staff'].queryset = StaffMember.objects.schedulable_staff()

        # For non-admins, make staff and branch fields not required
        # (they'll be auto-assigned by the view)
        if not is_admin:
            self.fields['staff'].required = False
            self.fields['branch'].required = False


class RecurringScheduleForm(FormControlMixin, forms.ModelForm):
    """Form for creating a recurring weekly schedule template."""

    days_of_week = forms.MultipleChoiceField(
        choices=RecurringSchedule.DayOfWeek.choices,
        widget=forms.CheckboxSelectMultiple(),
        label='Days of Week',
        help_text='Select one or more days',
    )

    class Meta:
        model = RecurringSchedule
        fields = [
            'staff', 'branch',
            'start_time', 'end_time', 'shift_type',
            'effective_from', 'effective_until',
        ]
        widgets = {
            'start_time': forms.TimeInput(attrs={'type': 'time'}),
            'end_time': forms.TimeInput(attrs={'type': 'time'}),
            'effective_from': forms.DateInput(attrs={'type': 'date'}),
            'effective_until': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, is_admin=True, **kwargs):
        super().__init__(*args, **kwargs)
        # Show staff who can be scheduled (using centralized manager method)
        self.fields['staff'].queryset = StaffMember.objects.schedulable_staff()

        # For non-admins, make staff and branch fields not required
        # (they'll be auto-assigned by the view)
        if not is_admin:
            self.fields['staff'].required = False
            self.fields['branch'].required = False
