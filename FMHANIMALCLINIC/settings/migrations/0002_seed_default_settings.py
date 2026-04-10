"""Data migration to seed default system settings."""

from django.db import migrations


def seed_default_settings(apps, schema_editor):
    """Seed default system settings."""
    SystemSetting = apps.get_model('settings', 'SystemSetting')
    ClinicProfile = apps.get_model('settings', 'ClinicProfile')

    # Default settings to seed
    defaults = [
        # Appointment Settings
        {'key': 'appointment_slot_duration', 'value': '30', 'value_type': 'integer',
         'category': 'APPOINTMENT', 'description': 'Duration of each appointment slot in minutes'},
        {'key': 'appointment_max_advance_days', 'value': '30', 'value_type': 'integer',
         'category': 'APPOINTMENT', 'description': 'Maximum days in advance for booking'},
        {'key': 'appointment_min_advance_hours', 'value': '2', 'value_type': 'integer',
         'category': 'APPOINTMENT', 'description': 'Minimum hours notice required for booking'},
        {'key': 'appointment_allow_walk_ins', 'value': 'true', 'value_type': 'boolean',
         'category': 'APPOINTMENT', 'description': 'Allow walk-in appointments'},
        {'key': 'appointment_daily_limit', 'value': '0', 'value_type': 'integer',
         'category': 'APPOINTMENT', 'description': 'Max appointments per day per branch (0 = unlimited)'},
        {'key': 'appointment_require_confirmation', 'value': 'true', 'value_type': 'boolean',
         'category': 'APPOINTMENT', 'description': 'Require admin confirmation for online bookings'},
        {'key': 'appointment_auto_cancel_hours', 'value': '24', 'value_type': 'integer',
         'category': 'APPOINTMENT', 'description': 'Auto-cancel unconfirmed appointments after this many hours'},
        {'key': 'appointment_reminder_hours', 'value': '24', 'value_type': 'integer',
         'category': 'APPOINTMENT', 'description': 'Hours before appointment to send reminder'},

        # Inventory Settings
        {'key': 'inventory_low_stock_threshold', 'value': '10', 'value_type': 'integer',
         'category': 'INVENTORY', 'description': 'Low stock warning level'},
        {'key': 'inventory_critical_threshold', 'value': '5', 'value_type': 'integer',
         'category': 'INVENTORY', 'description': 'Critical stock alert level'},
        {'key': 'inventory_enable_alerts', 'value': 'true', 'value_type': 'boolean',
         'category': 'INVENTORY', 'description': 'Enable stock notifications'},
        {'key': 'inventory_allow_negative', 'value': 'false', 'value_type': 'boolean',
         'category': 'INVENTORY', 'description': 'Allow selling when stock is zero'},
        {'key': 'inventory_expiry_warning_days', 'value': '30', 'value_type': 'integer',
         'category': 'INVENTORY', 'description': 'Warn this many days before product expiry'},

        # Notification Settings
        {'key': 'notification_email_enabled', 'value': 'true', 'value_type': 'boolean',
         'category': 'NOTIFICATION', 'description': 'Enable email notifications'},
        {'key': 'notification_sms_enabled', 'value': 'false', 'value_type': 'boolean',
         'category': 'NOTIFICATION', 'description': 'Enable SMS notifications'},
        {'key': 'notification_sms_provider', 'value': '', 'value_type': 'string',
         'category': 'NOTIFICATION', 'description': 'SMS gateway provider'},
        {'key': 'notification_sms_api_key', 'value': '', 'value_type': 'string',
         'category': 'NOTIFICATION', 'description': 'SMS provider API key', 'is_sensitive': True},
        {'key': 'notification_from_email', 'value': 'noreply@fmhclinic.com', 'value_type': 'string',
         'category': 'NOTIFICATION', 'description': 'Sender email address'},
        {'key': 'notification_sender_name', 'value': 'FMH Animal Clinic', 'value_type': 'string',
         'category': 'NOTIFICATION', 'description': 'Sender display name'},

        # Payroll Settings
        {'key': 'payroll_period_type', 'value': 'SEMI_MONTHLY', 'value_type': 'string',
         'category': 'PAYROLL', 'description': 'Payroll period type'},
        {'key': 'payroll_work_hours_per_day', 'value': '8', 'value_type': 'integer',
         'category': 'PAYROLL', 'description': 'Standard work hours per day'},
        {'key': 'payroll_overtime_threshold', 'value': '8', 'value_type': 'integer',
         'category': 'PAYROLL', 'description': 'Hours after which overtime pay applies'},
        {'key': 'payroll_enable_sss', 'value': 'true', 'value_type': 'boolean',
         'category': 'PAYROLL', 'description': 'Enable SSS deduction'},
        {'key': 'payroll_enable_philhealth', 'value': 'true', 'value_type': 'boolean',
         'category': 'PAYROLL', 'description': 'Enable PhilHealth deduction'},
        {'key': 'payroll_enable_pagibig', 'value': 'true', 'value_type': 'boolean',
         'category': 'PAYROLL', 'description': 'Enable Pag-IBIG deduction'},
        {'key': 'payroll_enable_tax', 'value': 'true', 'value_type': 'boolean',
         'category': 'PAYROLL', 'description': 'Enable withholding tax'},

        # System Settings
        {'key': 'system_timezone', 'value': 'Asia/Manila', 'value_type': 'string',
         'category': 'SYSTEM', 'description': 'System timezone'},
        {'key': 'system_date_format', 'value': 'M d, Y', 'value_type': 'string',
         'category': 'SYSTEM', 'description': 'Date display format'},
        {'key': 'system_time_format', 'value': 'h:i A', 'value_type': 'string',
         'category': 'SYSTEM', 'description': 'Time display format'},
        {'key': 'system_currency', 'value': 'PHP', 'value_type': 'string',
         'category': 'SYSTEM', 'description': 'Currency code'},
        {'key': 'system_currency_symbol', 'value': '₱', 'value_type': 'string',
         'category': 'SYSTEM', 'description': 'Currency symbol'},
        {'key': 'system_maintenance_mode', 'value': 'false', 'value_type': 'boolean',
         'category': 'SYSTEM', 'description': 'Enable maintenance mode'},
        {'key': 'system_maintenance_message', 'value': '', 'value_type': 'string',
         'category': 'SYSTEM', 'description': 'Maintenance mode message'},
        {'key': 'system_session_timeout', 'value': '30', 'value_type': 'integer',
         'category': 'SYSTEM', 'description': 'Session timeout in minutes'},
        {'key': 'system_max_login_attempts', 'value': '5', 'value_type': 'integer',
         'category': 'SYSTEM', 'description': 'Max login attempts before lockout'},
        {'key': 'system_lockout_duration', 'value': '15', 'value_type': 'integer',
         'category': 'SYSTEM', 'description': 'Account lockout duration in minutes'},

        # Medical Records Settings
        {'key': 'medical_default_followup_days', 'value': '7', 'value_type': 'integer',
         'category': 'MEDICAL', 'description': 'Default follow-up period in days'},
        {'key': 'medical_require_diagnosis', 'value': 'true', 'value_type': 'boolean',
         'category': 'MEDICAL', 'description': 'Require diagnosis to close record'},
        {'key': 'medical_vaccination_reminders', 'value': 'true', 'value_type': 'boolean',
         'category': 'MEDICAL', 'description': 'Enable vaccination reminders'},
        {'key': 'medical_reminder_days_before', 'value': '7', 'value_type': 'integer',
         'category': 'MEDICAL', 'description': 'Days before vaccination due date to send reminder'},
    ]

    # Create settings
    for setting_data in defaults:
        is_sensitive = setting_data.pop('is_sensitive', False)
        SystemSetting.objects.get_or_create(
            key=setting_data['key'],
            defaults={
                **setting_data,
                'is_sensitive': is_sensitive,
            }
        )

    # Create default clinic profile
    ClinicProfile.objects.get_or_create(
        pk=1,
        defaults={
            'name': 'FMH Animal Clinic',
            'email': 'contact@fmhclinic.com',
            'phone': '+63 XXX XXX XXXX',
            'address': '',
            'tagline': 'Caring for your pets like family',
            'license_number': '',
        }
    )


def reverse_seed(apps, schema_editor):
    """Reverse the seed operation."""
    # We don't delete the data on reverse to prevent data loss


class Migration(migrations.Migration):
    """Data migration to seed default settings."""

    dependencies = [
        ('settings', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed_default_settings, reverse_seed),
    ]
