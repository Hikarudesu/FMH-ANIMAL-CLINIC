from django.db import migrations


def add_reservations_module(apps, schema_editor):
    """Add Reservations as a module with CRUD permissions."""
    Module = apps.get_model('accounts', 'Module')
    
    # Create Reservations module
    Module.objects.get_or_create(
        code='reservations',
        defaults={
            'name': 'Reservations',
            'description': 'Manage product reservations',
            'icon': 'bx-cart',
            'url_name': 'inventory:management',
            'display_order': 31,
            'is_active': True,
        }
    )
    
    # Remove the old can_manage_inventory special permission if it exists
    SpecialPermission = apps.get_model('accounts', 'SpecialPermission')
    SpecialPermission.objects.filter(code='can_manage_inventory').delete()


def remove_reservations_module(apps, schema_editor):
    """Remove Reservations module on rollback."""
    Module = apps.get_model('accounts', 'Module')
    Module.objects.filter(code='reservations').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0019_backfill_staff_notifications_module'),
    ]

    operations = [
        migrations.RunPython(add_reservations_module, reverse_code=remove_reservations_module),
    ]
