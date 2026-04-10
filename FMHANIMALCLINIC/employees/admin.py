from django.contrib import admin
from .models import StaffMember, VetSchedule, RecurringSchedule


@admin.register(StaffMember)
class StaffMemberAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'position', 'branch', 'is_active')
    list_filter = ('position', 'branch', 'is_active')
    search_fields = ('first_name', 'last_name', 'email')


@admin.register(VetSchedule)
class VetScheduleAdmin(admin.ModelAdmin):
    list_display = ('staff', 'date', 'start_time', 'end_time',
                    'branch', 'shift_type', 'is_available')
    list_filter = ('branch', 'shift_type', 'is_available')
    search_fields = ('staff__first_name', 'staff__last_name')


@admin.register(RecurringSchedule)
class RecurringScheduleAdmin(admin.ModelAdmin):
    list_display = ('staff', 'day_of_week', 'start_time',
                    'end_time', 'branch', 'shift_type', 'is_active')
    list_filter = ('branch', 'shift_type', 'is_active', 'day_of_week')
