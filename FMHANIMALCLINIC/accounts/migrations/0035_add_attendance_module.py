"""Add Attendance & Biometrics module to RBAC system."""
from django.db import migrations


def add_attendance_module(apps, schema_editor):
    """Add Attendance & Biometrics module."""
    Module = apps.get_model('accounts', 'Module')
    
    Module.objects.get_or_create(
        code='attendance',
        defaults={
            'name': 'Attendance & Biometrics',
            'icon': 'bx-fingerprint',
            'url_name': 'attendance:dashboard',
            'display_order': 14,
            'description': 'Biometric fingerprint attendance tracking and management',
        }
    )


def remove_attendance_module(apps, schema_editor):
    """Remove Attendance & Biometrics module."""
    Module = apps.get_model('accounts', 'Module')
    Module.objects.filter(code='attendance').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0034_alter_module_code'),
    ]

    operations = [
        migrations.RunPython(add_attendance_module, remove_attendance_module),
    ]
