# Rename inventory module to Inventory Management
from django.db import migrations


def rename_inventory_module(apps, schema_editor):
    """Rename inventory module display name to 'Inventory Management'."""
    Module = apps.get_model('accounts', 'Module')
    try:
        inventory_module = Module.objects.get(code='inventory')
        inventory_module.name = 'Inventory Management'
        inventory_module.save()
    except Module.DoesNotExist:
        pass


def revert_inventory_module(apps, schema_editor):
    """Revert inventory module name back to 'Inventory'."""
    Module = apps.get_model('accounts', 'Module')
    try:
        inventory_module = Module.objects.get(code='inventory')
        inventory_module.name = 'Inventory'
        inventory_module.save()
    except Module.DoesNotExist:
        pass


class Migration(migrations.Migration):
    dependencies = [
        ('accounts', '0015_add_special_permissions'),
    ]

    operations = [
        migrations.RunPython(rename_inventory_module, reverse_code=revert_inventory_module),
    ]
