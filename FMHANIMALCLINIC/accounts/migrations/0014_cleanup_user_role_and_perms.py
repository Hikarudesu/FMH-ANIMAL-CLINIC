"""
Data migration to:
1. Clean up users with the 'user' role (set assigned_role=NULL)
2. Delete the 'user' Role record
3. Delete any ModulePermission records with deprecated APPROVE/EXPORT types
"""
from django.db import migrations


def cleanup_user_role_and_deprecated_perms(apps, schema_editor):
    """Remove 'user' role and clean up deprecated permission types."""
    Role = apps.get_model('accounts', 'Role')
    User = apps.get_model('accounts', 'User')
    ModulePermission = apps.get_model('accounts', 'ModulePermission')

    # 1. Find users with the 'user' role and unassign them
    try:
        user_role = Role.objects.get(code='user')
        # Set assigned_role to NULL for all users with this role
        updated = User.objects.filter(assigned_role=user_role).update(assigned_role=None)
        if updated:
            print(f"  → Unassigned 'user' role from {updated} user(s)")
        # Delete the role
        user_role.delete()
        print("  → Deleted 'user' Role record")
    except Role.DoesNotExist:
        print("  → 'user' Role not found (already removed)")

    # 2. Delete deprecated APPROVE/EXPORT permission records
    deprecated_count = ModulePermission.objects.filter(
        permission_type__in=['APPROVE', 'EXPORT']
    ).delete()[0]
    if deprecated_count:
        print(f"  → Deleted {deprecated_count} deprecated APPROVE/EXPORT permission(s)")


def reverse_noop(apps, schema_editor):
    """No reverse migration — data cleanup is not reversible."""


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0013_rbac_per_module_branch_restrict'),
    ]

    operations = [
        migrations.RunPython(
            cleanup_user_role_and_deprecated_perms,
            reverse_noop,
        ),
    ]
