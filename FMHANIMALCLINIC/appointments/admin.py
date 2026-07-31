from django.contrib import admin
from .models import Appointment


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = ['pet_name', 'owner_name', 'branch', 'preferred_vet',
                    'appointment_date', 'appointment_time', 'status', 'source']
    list_filter = ['status', 'source', 'branch', 'appointment_date']
    search_fields = ['pet_name', 'owner_name', 'owner_email']
    date_hierarchy = 'appointment_date'
    readonly_fields = ['created_at']
