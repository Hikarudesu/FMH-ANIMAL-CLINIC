"""
Forms for the records application.
"""
from django import forms
from django.db.models import Q
from FMHANIMALCLINIC.form_mixins import FormControlMixin
from .models import MedicalRecord, RecordEntry
from branches.models import Branch


class MedicalRecordForm(FormControlMixin, forms.ModelForm):
    class Meta:
        model = MedicalRecord
        fields = [
            'branch', 'vet', 'date_recorded', 'weight', 'temperature',
            'history_clinical_signs', 'treatment', 'rx', 'ff_up'
        ]
        widgets = {
            'branch': forms.Select(attrs={'id': 'id_branch'}),
            'vet': forms.Select(attrs={'id': 'id_vet'}),
            'date_recorded': forms.DateInput(attrs={'type': 'date'}),
            'weight': forms.NumberInput(attrs={'step': '0.01', 'placeholder': 'Wt (kg)'}),
            'temperature': forms.NumberInput(attrs={'step': '0.1', 'placeholder': 'Temp (°C)'}),
            'history_clinical_signs': forms.Textarea(attrs={'rows': 3}),
            'treatment': forms.Textarea(attrs={'rows': 3}),
            'rx': forms.Textarea(attrs={'rows': 3}),
            'ff_up': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from employees.models import StaffMember

        self.fields['branch'].queryset = Branch.objects.filter(is_active=True)
        self.fields['branch'].empty_label = '— Select Branch —'

        # Get the base queryset for vets
        vet_queryset = StaffMember.objects.filter(
            is_active=True,
            position__in=['VETERINARIAN', 'BRANCH_ADMIN', 'ADMIN']
        )

        # If editing an existing record with a vet, ensure that vet is in the queryset
        # even if they don't match the current filter (preserves historical data)
        if self.instance and self.instance.pk and self.instance.vet:
            current_vet = self.instance.vet
            if current_vet not in vet_queryset:
                # Include the current vet in the queryset
                vet_queryset = StaffMember.objects.filter(
                    Q(id=current_vet.id) |
                    Q(is_active=True, position__in=['VETERINARIAN', 'BRANCH_ADMIN', 'ADMIN'])
                )

        self.fields['vet'].queryset = vet_queryset
        self.fields['vet'].empty_label = '— Select Vet —'
        self.fields['vet'].required = False


class RecordEntryForm(FormControlMixin, forms.ModelForm):
    class Meta:
        model = RecordEntry
        fields = [
            'vet', 'date_recorded', 'weight', 'temperature',
            'history_clinical_signs', 'treatment', 'rx', 'ff_up',
            'action_required',
        ]
        widgets = {
            'vet': forms.Select(attrs={'id': 'id_vet'}),
            'date_recorded': forms.DateInput(attrs={'type': 'date'}),
            'weight': forms.NumberInput(attrs={'step': '0.01', 'placeholder': 'Wt (kg)'}),
            'temperature': forms.NumberInput(attrs={'step': '0.1', 'placeholder': 'Temp (°C)'}),
            'history_clinical_signs': forms.Textarea(attrs={'rows': 3}),
            'treatment': forms.Textarea(attrs={'rows': 3}),
            'rx': forms.Textarea(attrs={'rows': 3}),
            'ff_up': forms.DateInput(attrs={'type': 'date'}),
            'action_required': forms.Select(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from employees.models import StaffMember

        # Get the base queryset for vets
        vet_queryset = StaffMember.objects.filter(
            is_active=True,
            position__in=['VETERINARIAN', 'BRANCH_ADMIN', 'ADMIN']
        )

        # If editing an existing entry with a vet, ensure that vet is in the queryset
        # even if they don't match the current filter (preserves historical data)
        if self.instance and self.instance.pk and self.instance.vet:
            current_vet = self.instance.vet
            if current_vet not in vet_queryset:
                # Include the current vet in the queryset
                vet_queryset = StaffMember.objects.filter(
                    Q(id=current_vet.id) |
                    Q(is_active=True, position__in=['VETERINARIAN', 'BRANCH_ADMIN', 'ADMIN'])
                )

        self.fields['vet'].queryset = vet_queryset
        self.fields['vet'].empty_label = '— Select Vet —'
        self.fields['vet'].required = False
