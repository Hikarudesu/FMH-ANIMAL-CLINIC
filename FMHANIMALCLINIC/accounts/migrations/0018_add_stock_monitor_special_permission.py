# Generated migration for adding stock monitor special permission
from django.db import migrations


def add_stock_monitor_permission(apps, schema_editor):
    """Add Stock Monitor special permission."""
    SpecialPermission = apps.get_model('accounts', 'SpecialPermission')
    
    # Create Stock Monitor special permission if it doesn't exist
    SpecialPermission.objects.get_or_create(
        code='can_access_stock_monitor',
        defaults={
            'name': 'Stock Monitor',
            'description': 'Access to view stock/inventory levels. Data is always restricted to the user\'s assigned branch only.'
        }
    )


def remove_stock_monitor_permission(apps, schema_editor):
    """Remove Stock Monitor special permission."""
    SpecialPermission = apps.get_model('accounts', 'SpecialPermission')
    SpecialPermission.objects.filter(code='can_access_stock_monitor').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0017_assign_pos_to_receptionist'),
    ]

    operations = [
        migrations.RunPython(add_stock_monitor_permission, remove_stock_monitor_permission),
    ]
