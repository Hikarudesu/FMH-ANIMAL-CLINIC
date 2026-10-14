from django.contrib import admin

from .models import Branch, BranchArchive


@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = ('name', 'branch_code', 'city', 'phone_number', 'is_active')
    list_filter = ('is_active', 'city', 'state')
    search_fields = ('name', 'branch_code', 'city')

    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'branch_code', 'clinic_license_number', 'is_active')
        }),
        ('Contact Details', {
            'fields': ('phone_number', 'email')
        }),
        ('Address', {
            'fields': ('address', 'city', 'state', 'zip_code')
        }),
        ('Operations', {
            'fields': ('operating_hours',)
        }),
        ('Google Maps Integration', {
            'fields': ('google_maps_embed_url', 'google_maps_link'),
            'description': 'Get embed URL from Google Maps: Share → Embed a map → Copy the src URL'
        }),
        ('Social Media Links', {
            'fields': ('facebook_url', 'instagram_url', 'messenger_url', 'tiktok_url'),
            'classes': ('collapse',)
        }),
        ('Landing Page Display', {
            'fields': ('display_order', 'badge_label'),
            'classes': ('collapse',)
        }),
    )

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(BranchArchive)
class BranchArchiveAdmin(admin.ModelAdmin):
    list_display = (
        'branch', 'created_at', 'sale_count', 'payroll_period_count', 'email_status',
    )
    list_filter = ('email_status', 'created_at')
    readonly_fields = (
        'branch', 'pdf_file', 'sale_count', 'payroll_period_count',
        'recipient_emails', 'email_status', 'email_error', 'created_at', 'sent_at',
    )
    actions = ('retry_archive_email',)

    @admin.action(description='Retry email delivery for selected archives')
    def retry_archive_email(self, request, queryset):
        from .archive import deliver_branch_archive_email

        sent_count = sum(
            deliver_branch_archive_email(archive_id)
            for archive_id in queryset.values_list('pk', flat=True)
        )
        self.message_user(request, f'{sent_count} archive email(s) sent.')

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
