from django.db import migrations


def restore_disease_geo_mapping_module(apps, schema_editor):
    Module = apps.get_model('accounts', 'Module')
    Module.objects.get_or_create(
        code='disease_geo_mapping',
        defaults={
            'name': 'Disease Geo Mapping',
            'description': 'Analyze branch-wide disease trends and seasonal outbreak signals.',
            'icon': 'bx-map',
            'url_name': 'disease_geo_mapping:dashboard',
            'display_order': 5,
            'is_active': True,
        },
    )


class Migration(migrations.Migration):
    dependencies = [
        ('accounts', '0036_alter_module_code'),
    ]

    operations = [
        migrations.RunPython(
            restore_disease_geo_mapping_module,
            migrations.RunPython.noop,
        ),
    ]
