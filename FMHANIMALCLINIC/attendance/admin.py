"""Django admin interface for Attendance and Biometrics."""
from django.contrib import admin
from .models import (
    BiometricDevice,
    AttendanceLog,
    DailyAttendance,
)


@admin.register(BiometricDevice)
class BiometricDeviceAdmin(admin.ModelAdmin):
    """Admin interface for BiometricDevice."""
    
    list_display = (
        'device_name',
        'device_serial',
        'branch',
        'connection_type',
        'status',
        'is_active',
        'last_sync_at',
    )
    list_filter = ('status', 'is_active', 'branch', 'connection_type')
    search_fields = ('device_name', 'device_serial', 'branch__name')
    readonly_fields = ('created_at', 'updated_at', 'last_sync_at')
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('branch', 'device_name', 'device_model', 'device_serial')
        }),
        ('Connection', {
            'fields': ('ip_address', 'port', 'connection_type')
        }),
        ('Status', {
            'fields': ('status', 'is_active', 'last_sync_at', 'sync_interval_minutes')
        }),
        ('Notes', {
            'fields': ('notes',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(AttendanceLog)
class AttendanceLogAdmin(admin.ModelAdmin):
    """Admin interface for AttendanceLog."""
    
    list_display = (
        'external_user_id',
        'punch_datetime',
        'punch_type',
        'sync_status',
        'device',
        'imported_at',
    )
    list_filter = ('punch_type', 'sync_status', 'device', 'punch_datetime')
    search_fields = ('external_user_id',)
    readonly_fields = ('imported_at', 'processed_at', 'raw_payload')
    
    fieldsets = (
        ('Device', {
            'fields': ('device', 'external_user_id')
        }),
        ('Punch Data', {
            'fields': ('punch_datetime', 'punch_type', 'source_record_id')
        }),
        ('Processing', {
            'fields': ('sync_status', 'sync_notes', 'raw_payload')
        }),
        ('Timestamps', {
            'fields': ('imported_at', 'processed_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(DailyAttendance)
class DailyAttendanceAdmin(admin.ModelAdmin):
    """Admin interface for DailyAttendance."""
    
    list_display = (
        'staff',
        'attendance_date',
        'status',
        'check_in',
        'check_out',
        'late_minutes',
        'is_approved',
    )
    list_filter = ('status', 'is_approved', 'is_present', 'attendance_date')
    search_fields = ('staff__first_name', 'staff__last_name')
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        ('Staff & Date', {
            'fields': ('staff', 'attendance_date')
        }),
        ('Expected Schedule', {
            'fields': ('expected_start', 'expected_end', 'expected_hours')
        }),
        ('Actual Punches', {
            'fields': ('check_in', 'check_out')
        }),
        ('Metrics', {
            'fields': ('total_work_minutes', 'late_minutes', 'overtime_minutes')
        }),
        ('Status', {
            'fields': ('status', 'is_present', 'is_approved', 'approved_by', 'approved_at')
        }),
        ('Manual Adjustment', {
            'fields': ('is_manually_adjusted', 'adjustment_notes', 'adjusted_by'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
