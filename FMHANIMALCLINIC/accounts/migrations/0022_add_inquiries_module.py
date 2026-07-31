from django.db import migrations


def add_inquiries_module(apps, schema_editor):
    Module = apps.get_model('accounts', 'Module')
    Module.objects.get_or_create(
        code='inquiries',
        defaults={
            'name': 'Inquiries',
            'icon': 'bx-envelope',
            'url_name': 'inquiries:list',
            'display_order': 24,
            'is_active': True,
        },
    )


def remove_inquiries_module(apps, schema_editor):
    Module = apps.get_model('accounts', 'Module')
    Module.objects.filter(code='inquiries').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0021_staffuser'),
    ]

    operations = [
        migrations.RunPython(add_inquiries_module, reverse_code=remove_inquiries_module),
    ]