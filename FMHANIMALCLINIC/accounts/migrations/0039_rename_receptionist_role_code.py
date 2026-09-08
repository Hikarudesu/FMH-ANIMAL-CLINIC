from django.db import migrations


def rename_cashier_role_code(apps, schema_editor):
    Role = apps.get_model('accounts', 'Role')
    Role.objects.filter(name='Cashier', code='receptionist').update(code='cashier')


class Migration(migrations.Migration):
    dependencies = [
        ('accounts', '0038_restore_disease_geo_mapping_module'),
    ]

    operations = [
        migrations.RunPython(rename_cashier_role_code, migrations.RunPython.noop),
    ]
