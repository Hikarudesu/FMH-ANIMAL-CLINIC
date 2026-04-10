from django.contrib import admin
from .models import FollowUp, Notification


@admin.register(FollowUp)
class FollowUpAdmin(admin.ModelAdmin):
    list_display = ('pet_name', 'follow_up_date',
                    'is_completed', 'created_by', 'created_at')
    list_filter = ('is_completed', 'follow_up_date')
    search_fields = ('pet_name',)


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('title', 'user', 'notification_type',
                    'is_read', 'created_at')
    list_filter = ('notification_type', 'is_read')
    search_fields = ('title', 'user__username')
