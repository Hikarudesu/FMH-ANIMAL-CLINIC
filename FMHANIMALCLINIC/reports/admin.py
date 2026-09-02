from django.contrib import admin

from .models import ScheduledReport, ScheduledReportDelivery


@admin.register(ScheduledReport)
class ScheduledReportAdmin(admin.ModelAdmin):
    list_display = ('name', 'frequency', 'is_active', 'next_run_at', 'last_run_at')
    list_filter = ('frequency', 'is_active')
    search_fields = ('name', 'recipients')


@admin.register(ScheduledReportDelivery)
class ScheduledReportDeliveryAdmin(admin.ModelAdmin):
    list_display = ('report', 'period_key', 'status', 'sent_at')
    list_filter = ('status',)
    search_fields = ('report__name', 'recipients')
    readonly_fields = ('report', 'period_key', 'recipients', 'status', 'error_message', 'sent_at')