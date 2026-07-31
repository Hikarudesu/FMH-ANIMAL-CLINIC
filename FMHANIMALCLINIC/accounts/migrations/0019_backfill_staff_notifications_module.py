from django.db import migrations


def backfill_staff_notifications(apps, schema_editor):
    Role = apps.get_model('accounts', 'Role')
    Module = apps.get_model('accounts', 'Module')
    ModulePermission = apps.get_model('accounts', 'ModulePermission')

    notifications = Module.objects.filter(code='notifications').first()
    if notifications is None:
        return

    staff_roles = Role.objects.filter(
        code__in=['branch_admin', 'veterinarian', 'receptionist', 'vet_assistant']
    )
    for role in staff_roles:
        ModulePermission.objects.get_or_create(
            role=role,
            module=notifications,
            permission_type='VIEW',
            defaults={'restrict_to_branch': True},
        )


def reverse_backfill_staff_notifications(apps, schema_editor):
    Role = apps.get_model('accounts', 'Role')
    Module = apps.get_model('accounts', 'Module')
    ModulePermission = apps.get_model('accounts', 'ModulePermission')

    notifications = Module.objects.filter(code='notifications').first()
    if notifications is None:
        return

    staff_roles = Role.objects.filter(
        code__in=['branch_admin', 'veterinarian', 'receptionist', 'vet_assistant']
    )
    ModulePermission.objects.filter(
        role__in=staff_roles,
        module=notifications,
        permission_type='VIEW',
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0018_add_stock_monitor_special_permission'),
    ]

    operations = [
        migrations.RunPython(
            backfill_staff_notifications,
            reverse_backfill_staff_notifications,
        ),
    ]
