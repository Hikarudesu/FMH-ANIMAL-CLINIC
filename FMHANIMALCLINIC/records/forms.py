"""
Forms for the records application.
"""
from django import forms
from django.db.models import Q
from FMHANIMALCLINIC.form_mixins import FormControlMixin
from .models import MedicalRecord, RecordEntry, MedicalFile
from branches.models import Branch
from settings.models import ClinicalStatus


class MedicalRecordForm(FormControlMixin, forms.ModelForm):
    action_required = forms.ModelChoiceField(
        queryset=ClinicalStatus.objects.none(),
        required=True,
        empty_label='— Select Clinical Action —',
    )

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
            user__is_active=True,
            position__in=['VETERINARIAN', 'BRANCH_ADMIN', 'ADMIN']
        )

        # If editing an existing record with a vet, ensure that vet is in the queryset
        # even if they don't match the current filter (preserves historical data)
        if self.instance and self.instance.pk and self.instance.vet:
            current_vet = self.instance.vet
            if current_vet in vet_queryset:
                pass
            elif current_vet.is_active and current_vet.user and current_vet.user.is_active:
                # Include the current vet in the queryset
                vet_queryset = StaffMember.objects.filter(
                    Q(id=current_vet.id) |
                    Q(
                        is_active=True,
                        user__is_active=True,
                        position__in=['VETERINARIAN', 'BRANCH_ADMIN', 'ADMIN'],
                    )
                )

        self.fields['vet'].queryset = vet_queryset
        self.fields['vet'].empty_label = '— Select Vet —'
        self.fields['vet'].required = True
        self.fields['branch'].required = True

        action_queryset = ClinicalStatus.objects.filter(is_active=True)
        latest_entry = self.instance.latest_entry if self.instance and self.instance.pk else None
        if latest_entry and latest_entry.action_required_id:
            action_queryset = ClinicalStatus.objects.filter(
                Q(is_active=True) | Q(pk=latest_entry.action_required_id)
            )
        self.fields['action_required'].queryset = action_queryset.order_by('order', 'name')
        if latest_entry and latest_entry.action_required_id:
            self.initial['action_required'] = latest_entry.action_required_id


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
            user__is_active=True,
            position__in=['VETERINARIAN', 'BRANCH_ADMIN', 'ADMIN']
        )

        # If editing an existing entry with a vet, ensure that vet is in the queryset
        # even if they don't match the current filter (preserves historical data)
        if self.instance and self.instance.pk and self.instance.vet:
            current_vet = self.instance.vet
            if current_vet in vet_queryset:
                pass
            elif current_vet.is_active and current_vet.user and current_vet.user.is_active:
                # Include the current vet in the queryset
                vet_queryset = StaffMember.objects.filter(
                    Q(id=current_vet.id) |
                    Q(
                        is_active=True,
                        user__is_active=True,
                        position__in=['VETERINARIAN', 'BRANCH_ADMIN', 'ADMIN'],
                    )
                )

        self.fields['vet'].queryset = vet_queryset
        self.fields['vet'].empty_label = '— Select Vet —'
        self.fields['vet'].required = True

        from settings.models import ClinicalStatus

        action_queryset = ClinicalStatus.objects.filter(is_active=True)
        if self.instance and self.instance.pk and self.instance.action_required_id:
            action_queryset = ClinicalStatus.objects.filter(
                Q(is_active=True) | Q(pk=self.instance.action_required_id)
            )
        self.fields['action_required'].queryset = action_queryset.order_by('order', 'name')
        self.fields['action_required'].required = True
        if not self.instance.pk and not self.initial.get('action_required'):
            self.initial['action_required'] = ClinicalStatus.get_default().pk
