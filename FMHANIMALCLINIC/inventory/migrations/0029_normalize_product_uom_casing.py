"""Normalize Product.unit_of_measurement to match settings-cased labels.

This migration maps stored unit values (often lowercase from legacy data)
to the exact label used in `inventory_uom_options` so the UI shows the
same casing administrators entered in Settings.
"""

from django.db import migrations


def normalize_uom_case(apps, schema_editor):
    Product = apps.get_model('inventory', 'Product')
    SystemSetting = apps.get_model('settings', 'SystemSetting')
    import json

    try:
        setting = SystemSetting.objects.get(key='inventory_uom_options')
        try:
            options = setting.get_typed_value()
        except Exception:
            try:
                options = json.loads(setting.value or '[]')
            except Exception:
                options = []
    except SystemSetting.DoesNotExist:
        options = []

    # Fallback default ordering (keeps earlier application defaults)
    if not options:
        options = [
            'piece', 'tablet', 'capsule', 'vial', 'bottle', 'box', 'pack',
            'can', 'strip', 'sachet', 'tube', 'ml', 'l', 'g', 'kg', 'set',
        ]

    mapping = {opt.strip().lower(): opt.strip() for opt in options if opt}

    for p in Product.objects.all():
        cur = (p.unit_of_measurement or '').strip()
        if not cur:
            continue
        key = cur.lower()
        if key in mapping and p.unit_of_measurement != mapping[key]:
            p.unit_of_measurement = mapping[key]
            p.save(update_fields=['unit_of_measurement'])


def reverse_normalize_uom_case(apps, schema_editor):
    # Irreversible normalization - no reverse
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0028_alter_product_item_type'),
    ]

    operations = [
        migrations.RunPython(normalize_uom_case, reverse_normalize_uom_case),
    ]
