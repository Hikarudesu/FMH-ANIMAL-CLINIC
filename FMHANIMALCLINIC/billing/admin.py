from django.contrib import admin
from django.utils.html import format_html
from .models import Service, CustomerStatement


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    """Admin configuration for Service."""
    list_display = ('name', 'price', 'cost', 'category', 'active')
    list_filter = ('active', 'category')
    search_fields = ('name', 'description', 'category')
    ordering = ('-created_at',)


@admin.register(CustomerStatement)
class CustomerStatementAdmin(admin.ModelAdmin):
    """Admin configuration for Customer Statements."""
    list_display = (
        'statement_number', 'patient_name', 'owner_name',
        'date', 'total_amount', 'balance', 'status_display',
        'created_by', 'action_buttons'
    )
    list_filter = ('status', 'date', 'created_at', 'branch')
    search_fields = ('statement_number', 'patient_name', 'owner_name')
    readonly_fields = ('statement_number', 'created_at', 'updated_at', 'released_at', 'sent_at')
    ordering = ('-created_at',)

    fieldsets = (
        ('Statement Information', {
            'fields': ('statement_number', 'patient_name', 'owner_name', 'date', 'customer')
        }),
        ('Service Charges', {
            'fields': (
                'consultation_fee', 'treatment', 'boarding', 'vaccination',
                'surgery', 'laboratory', 'grooming', 'others'
            )
        }),
        ('Totals', {
            'fields': ('total_amount', 'deposit', 'balance')
        }),
        ('Status & Notes', {
            'fields': ('status', 'notes')
        }),
        ('Metadata', {
            'fields': ('created_by', 'branch', 'created_at', 'updated_at', 'released_at', 'sent_at'),
            'classes': ('collapse',)
        }),
    )

    def status_display(self, obj):
        """Display colored status badge."""
        colors = {
            'DRAFT': 'orange',
            'RELEASED': 'green',
            'SENT': 'blue'
        }
        color = colors.get(obj.status, 'gray')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color, obj.get_status_display()
        )
    status_display.short_description = 'Status'

    def action_buttons(self, obj):
        """Display action buttons."""
        if obj.status == 'DRAFT':
            return format_html(
                '<a href="/billing/statement/{}/release/" '
                'style="background: green; color: white; padding: 4px 8px; '
                'text-decoration: none; border-radius: 3px; font-size: 11px;">Release</a>',
                obj.pk
            )
        elif obj.status == 'RELEASED':
            return '<span style="color: green;">✓ Released</span>'
        return '-'
    action_buttons.short_description = 'Actions'

    def save_model(self, request, obj, form, change):
        """Auto-set created_by when saving."""
        if not change:  # New object
            obj.created_by = request.user
            obj.branch = request.user.branch
        super().save_model(request, obj, form, change)
