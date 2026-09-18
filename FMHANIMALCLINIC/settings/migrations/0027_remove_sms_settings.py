from django.db import migrations


def remove_sms_settings(apps, schema_editor):
    SystemSetting = apps.get_model('settings', 'SystemSetting')
    SystemSetting.objects.filter(
        key__in=[
            'notification_sms_enabled',
            'notification_sms_provider',
            'notification_sms_api_key',
            'notification_sms_default_recipient',
        ]
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('settings', '0026_seed_inventory_item_type_options'),
    ]

    operations = [
        migrations.RunPython(remove_sms_settings, migrations.RunPython.noop),
    ]
