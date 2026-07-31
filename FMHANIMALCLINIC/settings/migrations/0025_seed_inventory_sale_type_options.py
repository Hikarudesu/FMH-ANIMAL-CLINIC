"""Seed default inventory sale type options."""

import json

from django.db import migrations


DEFAULT_INVENTORY_SALE_TYPE_OPTIONS = [
    {'value': 'piece', 'label': 'Per Piece'},
    {'value': 'batch', 'label': 'Per Batch/Pack'},
]


def seed_inventory_sale_type_options(apps, schema_editor):
    """Create the editable inventory sale category setting if it does not exist."""
    SystemSetting = apps.get_model('settings', 'SystemSetting')
    SystemSetting.objects.get_or_create(
        key='inventory_sale_type_options',
        defaults={
            'value': json.dumps(DEFAULT_INVENTORY_SALE_TYPE_OPTIONS),
            'value_type': 'json',
            'category': 'INVENTORY',
            'description': 'Available sale categories used in inventory product forms',
        },
    )


def reverse_seed_inventory_sale_type_options(apps, schema_editor):
    """Do not remove seeded settings on rollback."""


class Migration(migrations.Migration):
    dependencies = [
        ('settings', '0024_seed_inventory_uom_options'),
    ]

    operations = [
        migrations.RunPython(seed_inventory_sale_type_options, reverse_seed_inventory_sale_type_options),
    ]
