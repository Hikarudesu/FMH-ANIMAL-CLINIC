"""Django admin configuration for settings."""

from django.contrib import admin

from .models import SystemSetting, ClinicProfile, ReasonForVisit, ClinicalStatus, LegalDocument


@admin.register(SystemSetting)
class SystemSettingAdmin(admin.ModelAdmin):
    """Admin configuration for SystemSetting model."""

    list_display = ['key', 'value_display', 'value_type', 'category', 'is_sensitive', 'updated_at']
    list_filter = ['category', 'value_type', 'is_sensitive']
    search_fields = ['key', 'description']
    ordering = ['category', 'key']
    readonly_fields = ['created_at', 'updated_at']

    fieldsets = (
        (None, {
            'fields': ('key', 'value', 'value_type', 'category')
        }),
        ('Details', {
            'fields': ('description', 'is_sensitive')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def value_display(self, obj):
        """Display value, masking sensitive values."""
        if obj.is_sensitive and obj.value:
            return '••••••••'
        return obj.value[:50] + '...' if obj.value and len(obj.value) > 50 else obj.value

    value_display.short_description = 'Value'


@admin.register(ClinicProfile)
class ClinicProfileAdmin(admin.ModelAdmin):
    """Admin configuration for ClinicProfile model."""

    list_display = ['name', 'email', 'phone', 'updated_at']
    readonly_fields = ['created_at', 'updated_at']

    fieldsets = (
        ('Branding', {
            'fields': ('name', 'logo', 'tagline')
        }),
        ('Contact', {
            'fields': ('email', 'phone', 'address')
        }),
        ('Legal', {
            'fields': ('license_number',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def has_add_permission(self, request):
        """Prevent adding more than one clinic profile."""
        return not ClinicProfile.objects.exists()

    def has_delete_permission(self, request, obj=None):
        """Prevent deleting the clinic profile."""
        return False


@admin.register(ReasonForVisit)
class ReasonForVisitAdmin(admin.ModelAdmin):
    """Admin configuration for ReasonForVisit model."""

    list_display = ['name', 'code', 'order', 'is_active', 'updated_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['name', 'code', 'description']
    ordering = ['order', 'name']
    readonly_fields = ['created_at', 'updated_at']

    fieldsets = (
        (None, {
            'fields': ('name', 'code', 'description')
        }),
        ('Display', {
            'fields': ('order', 'is_active')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(ClinicalStatus)
class ClinicalStatusAdmin(admin.ModelAdmin):
    """Admin configuration for ClinicalStatus model."""

    list_display = ['name', 'code', 'color_display', 'order', 'is_active', 'updated_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['name', 'code', 'description']
    ordering = ['order', 'name']
    readonly_fields = ['created_at', 'updated_at']

    fieldsets = (
        (None, {
            'fields': ('name', 'code', 'description')
        }),
        ('Display', {
            'fields': ('color', 'order', 'is_active')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def color_display(self, obj):
        """Display color swatch."""
        return f'<div style="width: 20px; height: 20px; background-color: {obj.color}; border-radius: 4px;"></div>'

    color_display.short_description = 'Color'
    color_display.allow_tags = True


@admin.register(LegalDocument)
class LegalDocumentAdmin(admin.ModelAdmin):
    """Admin for managing legal documents (TOS, Privacy Policy)."""

    list_display = ['title', 'document_type', 'version', 'is_active', 'last_updated']
    list_filter = ['document_type', 'is_active']
    search_fields = ['title', 'content']
    readonly_fields = ['created_at', 'last_updated']

    fieldsets = (
        (None, {
            'fields': ('document_type', 'title', 'version', 'is_active')
        }),
        ('Content', {
            'fields': ('content',),
            'description': 'Enter the full document content. HTML formatting is supported.'
        }),
        ('Timestamps', {
            'fields': ('created_at', 'last_updated'),
            'classes': ('collapse',)
        }),
    )

