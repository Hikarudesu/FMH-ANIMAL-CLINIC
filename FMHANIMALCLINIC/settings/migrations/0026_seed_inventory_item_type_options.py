"""Seed default inventory item type options."""

from django.db import migrations
import json

DEFAULT_INVENTORY_ITEM_TYPE_OPTIONS = [
    'Product',
    'Medication',
    'Accessories',
    'Medical Supplies',
]


def seed_inventory_item_type_options(apps, schema_editor):
    SystemSetting = apps.get_model('settings', 'SystemSetting')
    SystemSetting.objects.get_or_create(
        key='inventory_item_type_options',
        defaults={
            'value': json.dumps(DEFAULT_INVENTORY_ITEM_TYPE_OPTIONS),
            'value_type': 'json',
            'category': 'INVENTORY',
            'description': 'Default inventory item type options',
        },
    )


def reverse_seed_inventory_item_type_options(apps, schema_editor):
    SystemSetting = apps.get_model('settings', 'SystemSetting')
    SystemSetting.objects.filter(key='inventory_item_type_options').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('settings', '0025_seed_inventory_sale_type_options'),
    ]

    operations = [
        migrations.RunPython(seed_inventory_item_type_options, reverse_seed_inventory_item_type_options),
    ]
