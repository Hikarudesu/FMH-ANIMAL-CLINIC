from django.db import migrations


def grant_receptionist_patient_transfer_permissions(apps, schema_editor):
    Role = apps.get_model('accounts', 'Role')
    Module = apps.get_model('accounts', 'Module')
    ModulePermission = apps.get_model('accounts', 'ModulePermission')

    patients = Module.objects.filter(code='patients').first()
    if patients is None:
        return

    roles = Role.objects.filter(code__in=('cashier', 'receptionist'))
    for role in roles:
        for permission_type in ('VIEW', 'EDIT'):
            permission, _ = ModulePermission.objects.get_or_create(
                role=role,
                module=patients,
                permission_type=permission_type,
            )
            if not permission.restrict_to_branch:
                permission.restrict_to_branch = True
                permission.save(update_fields=['restrict_to_branch'])


def revoke_receptionist_patient_transfer_permissions(apps, schema_editor):
    Role = apps.get_model('accounts', 'Role')
    Module = apps.get_model('accounts', 'Module')
    ModulePermission = apps.get_model('accounts', 'ModulePermission')

    patients = Module.objects.filter(code='patients').first()
    if patients is None:
        return

    ModulePermission.objects.filter(
        role__code__in=('cashier', 'receptionist'),
        module=patients,
        permission_type__in=('VIEW', 'EDIT'),
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('accounts', '0045_grant_cashier_patient_transfer_permissions'),
    ]

    operations = [
        migrations.RunPython(
            grant_receptionist_patient_transfer_permissions,
            revoke_receptionist_patient_transfer_permissions,
        ),
    ]
