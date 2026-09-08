"""Django admin interface for Attendance and Biometrics."""
from django.contrib import admin
from .models import DailyAttendance


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
