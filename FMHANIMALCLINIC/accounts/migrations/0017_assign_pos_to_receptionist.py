# Assign POS special permission to receptionist role
from django.db import migrations


def assign_pos_to_receptionist(apps, schema_editor):
    """Assign POS special permission to receptionist role."""
    Role = apps.get_model('accounts', 'Role')
    SpecialPermission = apps.get_model('accounts', 'SpecialPermission')
    RoleSpecialPermission = apps.get_model('accounts', 'RoleSpecialPermission')
    
    try:
        receptionist_role = Role.objects.get(code='receptionist')
        pos_permission = SpecialPermission.objects.get(code='can_access_pos')
        
        # Check if the relationship already exists
        if not RoleSpecialPermission.objects.filter(
            role=receptionist_role, 
            permission=pos_permission
        ).exists():
            RoleSpecialPermission.objects.create(
                role=receptionist_role,
                permission=pos_permission
            )
            
    except (Role.DoesNotExist, SpecialPermission.DoesNotExist):
        # Roles or permissions don't exist yet
        pass


def remove_pos_from_receptionist(apps, schema_editor):
    """Remove POS special permission from receptionist role."""
    Role = apps.get_model('accounts', 'Role')
    SpecialPermission = apps.get_model('accounts', 'SpecialPermission')
    RoleSpecialPermission = apps.get_model('accounts', 'RoleSpecialPermission')
    
    try:
        receptionist_role = Role.objects.get(code='receptionist')
        pos_permission = SpecialPermission.objects.get(code='can_access_pos')
        
        RoleSpecialPermission.objects.filter(
            role=receptionist_role,
            permission=pos_permission
        ).delete()
            
    except (Role.DoesNotExist, SpecialPermission.DoesNotExist):
        pass


class Migration(migrations.Migration):
    dependencies = [
        ('accounts', '0016_rename_inventory_module'),
    ]

    operations = [
        migrations.RunPython(assign_pos_to_receptionist, reverse_code=remove_pos_from_receptionist),
    ]