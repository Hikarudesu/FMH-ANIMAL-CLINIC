from django.db import migrations


def grant_cashier_appointment_visibility(apps, schema_editor):
    Role = apps.get_model('accounts', 'Role')
    Module = apps.get_model('accounts', 'Module')
    ModulePermission = apps.get_model('accounts', 'ModulePermission')

    cashier = Role.objects.filter(code='cashier').first()
    appointments = Module.objects.filter(code='appointments').first()
    if cashier is None or appointments is None:
        return

    ModulePermission.objects.get_or_create(
        role=cashier,
        module=appointments,
        permission_type='VIEW',
        defaults={'restrict_to_branch': True},
    )


def revoke_cashier_appointment_visibility(apps, schema_editor):
    Role = apps.get_model('accounts', 'Role')
    Module = apps.get_model('accounts', 'Module')
    ModulePermission = apps.get_model('accounts', 'ModulePermission')

    cashier = Role.objects.filter(code='cashier').first()
    appointments = Module.objects.filter(code='appointments').first()
    if cashier is None or appointments is None:
        return

    ModulePermission.objects.filter(
        role=cashier,
        module=appointments,
        permission_type='VIEW',
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('accounts', '0040_rename_existing_role_codes'),
    ]

    operations = [
        migrations.RunPython(
            grant_cashier_appointment_visibility,
            revoke_cashier_appointment_visibility,
        ),
    ]
