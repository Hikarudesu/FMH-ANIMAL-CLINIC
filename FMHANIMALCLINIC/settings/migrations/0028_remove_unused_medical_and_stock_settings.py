from django.db import migrations


def remove_unused_settings(apps, schema_editor):
    SystemSetting = apps.get_model('settings', 'SystemSetting')
    SystemSetting.objects.filter(
        key__in=[
            'medical_default_followup_days',
            'medical_vaccination_reminders',
            'medical_reminder_days_before',
            'medical_clinical_status_auto_actions',
            'inventory_allow_negative',
        ]
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('settings', '0027_remove_sms_settings'),
    ]

    operations = [
        migrations.RunPython(remove_unused_settings, migrations.RunPython.noop),
    ]
