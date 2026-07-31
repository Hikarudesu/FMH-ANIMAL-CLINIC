from django.db import migrations


def create_module_record(apps, schema_editor):
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
        ('disease_geo_mapping', '0001_initial'),
        ('accounts', '0006_rbac_models'),
    ]

    operations = [
        migrations.RunPython(create_module_record, migrations.RunPython.noop),
    ]
