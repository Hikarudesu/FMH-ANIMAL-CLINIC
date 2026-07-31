from django.contrib import admin
from .models import AIDiagnosis


@admin.register(AIDiagnosis)
class AIDiagnosisAdmin(admin.ModelAdmin):
    list_display = ['pet', 'primary_condition', 'created_at', 'is_reviewed']
    list_filter = ['is_reviewed', 'created_at']
    search_fields = ['pet__name', 'primary_condition', 'summary']
    readonly_fields = ['created_at', 'raw_response']
    ordering = ['-created_at']
