"""
Django Administration config for the Records application.
"""
from django.contrib import admin
from .models import MedicalRecord, RecordEntry


class RecordEntryInline(admin.TabularInline):
    """Inline editor for visit entries on a MedicalRecord."""
    model = RecordEntry
    extra = 1
    fields = ('date_recorded', 'vet', 'weight', 'temperature',
              'history_clinical_signs', 'treatment', 'rx', 'lab_results', 'ff_up', 'action_required')


@admin.register(MedicalRecord)
class MedicalRecordAdmin(admin.ModelAdmin):
    """Admin interface customization for the MedicalRecord model."""
    list_display = ('pet', 'vet', 'branch', 'date_recorded', 'treatment', 'lab_results')
    list_filter = ('branch', 'vet', 'date_recorded')
    search_fields = ('pet__name', 'history_clinical_signs', 'treatment', 'lab_results')
    autocomplete_fields = ('pet', 'vet')
    inlines = [RecordEntryInline]


@admin.register(RecordEntry)
class RecordEntryAdmin(admin.ModelAdmin):
    """Admin interface customization for the RecordEntry model."""
    list_display = ('record', 'date_recorded', 'vet', 'weight', 'temperature', 'action_required')
    list_filter = ('date_recorded', 'vet', 'action_required')
    search_fields = ('record__pet__name', 'history_clinical_signs', 'treatment', 'lab_results')
