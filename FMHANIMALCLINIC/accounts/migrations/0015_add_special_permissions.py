# Add new special permissions for module access control
from django.db import migrations


def add_special_permissions(apps, schema_editor):
    """Add new special permissions for dashboard and POS access."""
    SpecialPermission = apps.get_model('accounts', 'SpecialPermission')

    new_permissions = [
        # ─── Dashboard Access ──────────────────────────────────────
        {
            'code': 'can_access_staff_dashboard',
            'name': 'Staff Dashboard Access',
            'description': 'Can view the staff dashboard with basic clinic information and statistics'
        },
        {
            'code': 'can_access_admin_dashboard',
            'name': 'Admin Dashboard Access',
            'description': 'Can view the admin dashboard with advanced statistics and management options'
        },

        # ─── Point of Sale ─────────────────────────────────────────
        {
            'code': 'can_access_pos',
            'name': 'Point of Sale Access',
            'description': 'Full access to Point of Sale module (checkout, sales, refunds). Data restricted to own branch.'
        },
    ]

    for perm in new_permissions:
        SpecialPermission.objects.get_or_create(code=perm['code'], defaults=perm)

    # Update the manage_own_schedule permission description if it exists
    try:
        manage_schedule = SpecialPermission.objects.get(code='can_manage_own_schedule')
        manage_schedule.description = (
            'Can view only their own schedule entries and create/edit/delete only their own schedule entries. '
            'Cannot view or modify schedules of other staff members.'
        )
        manage_schedule.save()
    except SpecialPermission.DoesNotExist:
        SpecialPermission.objects.create(
            code='can_manage_own_schedule',
            name='Manage Own Schedule',
            description=(
                'Can view only their own schedule entries and create/edit/delete only their own schedule entries. '
                'Cannot view or modify schedules of other staff members.'
            )
        )


def remove_special_permissions(apps, schema_editor):
    """Remove the new special permissions."""
    SpecialPermission = apps.get_model('accounts', 'SpecialPermission')
    SpecialPermission.objects.filter(code__in=[
        'can_access_staff_dashboard',
        'can_access_admin_dashboard',
        'can_access_pos',
    ]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('accounts', '0014_cleanup_user_role_and_perms'),
    ]

    operations = [
        migrations.RunPython(add_special_permissions, reverse_code=remove_special_permissions),
    ]
