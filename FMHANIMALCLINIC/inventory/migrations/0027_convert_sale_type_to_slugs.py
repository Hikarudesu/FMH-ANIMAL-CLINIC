"""Convert legacy underscore sale_type values to hyphenated slugs.

This migration updates existing Product.sale_type values like 'per_piece'
into 'per-piece' so that they match the current settings-driven choice
slugs produced by `settings.utils.get_inventory_sale_type_choices`.
"""

from django.db import migrations


def migrate_sale_types(apps, schema_editor):
    Product = apps.get_model('inventory', 'Product')
    for p in Product.objects.all():
        cur = (p.sale_type or '').strip()
        if not cur:
            continue
        if '_' in cur:
            new = cur.replace('_', '-')
            if new != cur:
                p.sale_type = new
                p.save(update_fields=['sale_type'])


def reverse_migration(apps, schema_editor):
    # No-op reverse — cannot reliably map back to legacy underscores.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0026_alter_product_sale_type'),
    ]

    operations = [
        migrations.RunPython(migrate_sale_types, reverse_migration),
    ]
