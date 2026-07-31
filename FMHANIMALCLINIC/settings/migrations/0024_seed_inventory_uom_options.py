"""Seed default inventory unit options."""

import json

from django.db import migrations


DEFAULT_INVENTORY_UOM_OPTIONS = [
    'piece',
    'tablet',
    'capsule',
    'vial',
    'bottle',
    'box',
    'pack',
    'can',
    'strip',
    'sachet',
    'tube',
    'ml',
    'l',
    'g',
    'kg',
    'set',
]


def seed_inventory_uom_options(apps, schema_editor):
    """Create the editable inventory UOM setting if it does not exist."""
    SystemSetting = apps.get_model('settings', 'SystemSetting')
    SystemSetting.objects.get_or_create(
        key='inventory_uom_options',
        defaults={
            'value': json.dumps(DEFAULT_INVENTORY_UOM_OPTIONS),
            'value_type': 'json',
            'category': 'INVENTORY',
            'description': 'Available units of measurement used in inventory product forms',
        },
    )


def reverse_seed_inventory_uom_options(apps, schema_editor):
    """Do not remove seeded settings on rollback."""


class Migration(migrations.Migration):
    dependencies = [
        ('settings', '0023_merge_20260503_0328'),
    ]

    operations = [
        migrations.RunPython(seed_inventory_uom_options, reverse_seed_inventory_uom_options),
    ]
