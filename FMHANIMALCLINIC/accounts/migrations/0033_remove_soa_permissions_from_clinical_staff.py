from django.db import migrations


def remove_soa_permissions(apps, schema_editor):
    Role = apps.get_model('accounts', 'Role')
    ModulePermission = apps.get_model('accounts', 'ModulePermission')

    for role_code in ('veterinarian', 'vet_assistant'):
        role = Role.objects.filter(code=role_code).first()
        if role:
            ModulePermission.objects.filter(role=role, module__code='soa').delete()


def restore_soa_permissions(apps, schema_editor):
    Role = apps.get_model('accounts', 'Role')
    Module = apps.get_model('accounts', 'Module')
    ModulePermission = apps.get_model('accounts', 'ModulePermission')

    soa_module = Module.objects.filter(code='soa').first()
    if not soa_module:
        return

    for role_code in ('veterinarian', 'vet_assistant'):
        role = Role.objects.filter(code=role_code).first()
        if role:
            ModulePermission.objects.get_or_create(
                role=role,
                module=soa_module,
                permission_type='VIEW',
            )


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0032_fix_receptionist_role_permissions'),
    ]

    operations = [
        migrations.RunPython(remove_soa_permissions, reverse_code=restore_soa_permissions),
    ]