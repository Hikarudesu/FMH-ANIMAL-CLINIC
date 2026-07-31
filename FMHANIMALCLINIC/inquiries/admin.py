from django.contrib import admin
from django.utils.html import format_html
from .models import Inquiry
from notifications.utils import notify_inquiry_archived, notify_inquiry_responded


@admin.register(Inquiry)
class InquiryAdmin(admin.ModelAdmin):
    list_display = [
        'full_name', 'email', 'phone', 'branch', 
        'status_badge', 'priority_badge', 'created_at'
    ]
    list_filter = ['status', 'priority', 'branch', 'created_at']
    search_fields = ['full_name', 'email', 'phone', 'message']
    readonly_fields = ['created_at', 'updated_at']
    date_hierarchy = 'created_at'
    ordering = ['-created_at']
    
    fieldsets = (
        ('Contact Information', {
            'fields': ('full_name', 'email', 'phone', 'branch')
        }),
        ('Inquiry Details', {
            'fields': ('message', 'status', 'priority')
        }),
        ('Response', {
            'fields': ('response', 'responded_by', 'response_date'),
            'classes': ('collapse',)
        }),
        ('Internal', {
            'fields': ('internal_notes', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def status_badge(self, obj):
        colors = {
            'NEW': '#e74c3c',      # Red
            'READ': '#3498db',     # Blue
            'RESPONDED': '#27ae60', # Green
            'ARCHIVED': '#95a5a6',  # Gray
        }
        color = colors.get(obj.status, '#95a5a6')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; '
            'border-radius: 12px; font-size: 11px; font-weight: 600;">{}</span>',
            color, obj.get_status_display()
        )
    status_badge.short_description = 'Status'
    status_badge.admin_order_field = 'status'
    
    def priority_badge(self, obj):
        colors = {
            'LOW': '#95a5a6',
            'NORMAL': '#3498db',
            'HIGH': '#e67e22',
            'URGENT': '#e74c3c',
        }
        color = colors.get(obj.priority, '#3498db')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; '
            'border-radius: 12px; font-size: 11px; font-weight: 600;">{}</span>',
            color, obj.get_priority_display()
        )
    priority_badge.short_description = 'Priority'
    priority_badge.admin_order_field = 'priority'
    
    def save_model(self, request, obj, form, change):
        previous_status = None
        if change and obj.pk:
            previous_status = Inquiry.objects.filter(pk=obj.pk).values_list('status', flat=True).first()

        # Auto-populate responded_by when response is added
        if obj.response and not obj.responded_by:
            obj.responded_by = request.user
            from django.utils import timezone
            obj.response_date = timezone.now()
            if obj.status == 'NEW' or obj.status == 'READ':
                obj.status = 'RESPONDED'
        super().save_model(request, obj, form, change)

        if obj.status == 'RESPONDED' and previous_status != 'RESPONDED':
            notify_inquiry_responded(obj, request.user)
        elif obj.status == 'ARCHIVED' and previous_status != 'ARCHIVED':
            notify_inquiry_archived(obj, request.user)
