"""
Django Administration config for the Records application.
"""
from django.contrib import admin
from .models import MedicalFile, MedicalFileAccessLog, MedicalRecord, RecordEntry


class RecordEntryInline(admin.TabularInline):
    """Inline editor for visit entries on a MedicalRecord."""
    model = RecordEntry
    extra = 1
    fields = ('date_recorded', 'vet', 'weight', 'temperature',
              'history_clinical_signs', 'treatment', 'rx', 'ff_up', 'action_required')


@admin.register(MedicalRecord)
class MedicalRecordAdmin(admin.ModelAdmin):
    """Admin interface customization for the MedicalRecord model."""
    list_display = ('pet', 'vet', 'branch', 'date_recorded', 'treatment')
    list_filter = ('branch', 'vet', 'date_recorded')
    search_fields = ('pet__name', 'history_clinical_signs', 'treatment')
    autocomplete_fields = ('pet', 'vet')
    inlines = [RecordEntryInline]


@admin.register(RecordEntry)
class RecordEntryAdmin(admin.ModelAdmin):
    """Admin interface customization for the RecordEntry model."""
    list_display = ('record', 'date_recorded', 'vet', 'weight', 'temperature', 'action_required')
    list_filter = ('date_recorded', 'vet', 'action_required')
    search_fields = ('record__pet__name', 'history_clinical_signs', 'treatment')


@admin.register(MedicalFile)
class MedicalFileAdmin(admin.ModelAdmin):
    list_display = ('original_name', 'record', 'file_type', 'uploaded_by', 'uploaded_at')
    list_filter = ('file_type', 'uploaded_at')
    search_fields = ('original_name', 'record__pet__name', 'sha256')
    readonly_fields = ('sha256', 'uploaded_at')


@admin.register(MedicalFileAccessLog)
class MedicalFileAccessLogAdmin(admin.ModelAdmin):
    list_display = ('medical_file', 'user', 'action', 'success', 'ip_address', 'created_at')
    list_filter = ('action', 'success', 'created_at')
    search_fields = ('medical_file__original_name', 'user__username', 'ip_address')
    readonly_fields = ('medical_file', 'user', 'action', 'success', 'ip_address', 'created_at', 'detail')
