from django.contrib import admin

from .models import Branch


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
