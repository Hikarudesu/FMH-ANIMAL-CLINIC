from django.db import migrations


def remove_notification_email_settings(apps, schema_editor):
    SystemSetting = apps.get_model('settings', 'SystemSetting')
    SystemSetting.objects.filter(
        key__in=[
            'notification_email_enabled',
            'notification_from_email',
            'notification_sender_name',
        ]
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('settings', '0028_remove_unused_medical_and_stock_settings'),
    ]

    operations = [
        migrations.RunPython(
            remove_notification_email_settings,
            migrations.RunPython.noop,
        ),
    ]