from django.db import migrations


def grant_cashier_patient_transfer_permissions(apps, schema_editor):
    Role = apps.get_model('accounts', 'Role')
    Module = apps.get_model('accounts', 'Module')
    ModulePermission = apps.get_model('accounts', 'ModulePermission')

    cashier = Role.objects.filter(code='cashier').first()
    patients = Module.objects.filter(code='patients').first()
    if cashier is None or patients is None:
        return

    for permission_type in ('VIEW', 'EDIT'):
        permission, _ = ModulePermission.objects.get_or_create(
            role=cashier,
            module=patients,
            permission_type=permission_type,
        )
        if not permission.restrict_to_branch:
            permission.restrict_to_branch = True
            permission.save(update_fields=['restrict_to_branch'])


def revoke_cashier_patient_transfer_permissions(apps, schema_editor):
    Role = apps.get_model('accounts', 'Role')
    Module = apps.get_model('accounts', 'Module')
    ModulePermission = apps.get_model('accounts', 'ModulePermission')

    cashier = Role.objects.filter(code='cashier').first()
    patients = Module.objects.filter(code='patients').first()
    if cashier is None or patients is None:
        return

    ModulePermission.objects.filter(
        role=cashier,
        module=patients,
        permission_type__in=('VIEW', 'EDIT'),
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('accounts', '0044_user_owner_account_deactivated_at_and_more'),
    ]

    operations = [
        migrations.RunPython(
            grant_cashier_patient_transfer_permissions,
            revoke_cashier_patient_transfer_permissions,
        ),
    ]
