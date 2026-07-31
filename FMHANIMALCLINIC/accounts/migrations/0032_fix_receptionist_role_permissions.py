# Fix receptionist role module permissions - clean and rebuild
from django.db import migrations


def fix_receptionist_permissions(apps, schema_editor):
    """
    Fix receptionist role permissions to match correct business logic.
    
    Receptionist should have (based on business requirements):
    - appointments: VIEW, CREATE, EDIT, DELETE
    - patients: VIEW, CREATE, EDIT
    - pos: VIEW, CREATE, EDIT
    - schedule: VIEW, CREATE, EDIT, DELETE
    - clinic_services: VIEW
    - inventory: VIEW, CREATE, EDIT, DELETE (FULL CRUD)
    - reservations: VIEW, CREATE, EDIT, DELETE
    - stock_monitor: VIEW
    - notifications: VIEW
    """
    Role = apps.get_model('accounts', 'Role')
    Module = apps.get_model('accounts', 'Module')
    ModulePermission = apps.get_model('accounts', 'ModulePermission')
    
    try:
        receptionist_role = Role.objects.get(code='receptionist')
    except Role.DoesNotExist:
        return
    
    # Delete all existing permissions for receptionist to clean slate
    ModulePermission.objects.filter(role=receptionist_role).delete()
    
    # Define correct permissions based on business requirements
    correct_permissions = {
        'appointments': ['VIEW', 'CREATE', 'EDIT', 'DELETE'],
        'patients': ['VIEW', 'CREATE', 'EDIT'],
        'pos': ['VIEW', 'CREATE', 'EDIT'],
        'schedule': ['VIEW', 'CREATE', 'EDIT', 'DELETE'],
        'clinic_services': ['VIEW'],
        'inventory': ['VIEW', 'CREATE', 'EDIT', 'DELETE'],
        'reservations': ['VIEW', 'CREATE', 'EDIT', 'DELETE'],
        'stock_monitor': ['VIEW'],
        'notifications': ['VIEW'],
    }
    
    # Add correct permissions
    for module_code, permission_types in correct_permissions.items():
        try:
            module = Module.objects.get(code=module_code)
            for perm_type in permission_types:
                ModulePermission.objects.get_or_create(
                    role=receptionist_role,
                    module=module,
                    permission_type=perm_type
                )
        except Module.DoesNotExist:
            pass  # Module doesn't exist, skip it


def reverse_fix_receptionist_permissions(apps, schema_editor):
    """Reverse the migration - restore to previous state if needed."""
    # Note: This would restore broken state, but we keep it for consistency
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0031_reorganize_module_display_order'),
    ]

    operations = [
        migrations.RunPython(fix_receptionist_permissions, reverse_code=reverse_fix_receptionist_permissions),
    ]
