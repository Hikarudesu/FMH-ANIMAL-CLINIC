"""Attendance app configuration."""
from django.apps import AppConfig


class AttendanceConfig(AppConfig):
    """Configuration for the Attendance app."""
    
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'attendance'
    verbose_name = 'Attendance & Biometrics'
