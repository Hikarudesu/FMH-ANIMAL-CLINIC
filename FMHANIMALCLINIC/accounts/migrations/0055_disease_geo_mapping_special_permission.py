from django.db import migrations


def move_disease_geo_mapping_access(apps, schema_editor):
    Module = apps.get_model('accounts', 'Module')
    ModulePermission = apps.get_model('accounts', 'ModulePermission')
    Role = apps.get_model('accounts', 'Role')
    SpecialPermission = apps.get_model('accounts', 'SpecialPermission')
    RoleSpecialPermission = apps.get_model('accounts', 'RoleSpecialPermission')

    permission, _ = SpecialPermission.objects.get_or_create(
        code='can_access_disease_geo_mapping',
        defaults={
            'name': 'Access Disease Geo Mapping',
            'description': 'View disease trends for the assigned branch only.',
        },
    )

    module_permissions = ModulePermission.objects.filter(
        module__code='disease_geo_mapping',
    )
    role_ids = set(module_permissions.values_list('role_id', flat=True))
    role_ids.update(
        Role.objects.filter(hierarchy_level__gte=5).values_list('id', flat=True)
    )
    veterinarian = Role.objects.filter(code='veterinarian').first()
    if veterinarian:
        role_ids.add(veterinarian.pk)

    for role_id in role_ids:
        RoleSpecialPermission.objects.get_or_create(
            role_id=role_id,
            permission=permission,
        )

    module_permissions.delete()
    Module.objects.filter(code='disease_geo_mapping').update(is_active=False)


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0054_activitylog_timestamp_index'),
        ('disease_geo_mapping', '0004_remove_diseasegeomappinginsight_branch_and_more'),
    ]

    operations = [
        migrations.RunPython(
            move_disease_geo_mapping_access,
            migrations.RunPython.noop,
        ),
    ]