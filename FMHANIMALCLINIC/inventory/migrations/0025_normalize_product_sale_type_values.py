"""Normalize existing product sale type values to slugified category keys."""

from django.db import migrations


SALE_TYPE_VALUE_MAP = {
    'piece': 'per_piece',
    'per piece': 'per_piece',
    'batch': 'per_batch_pack',
    'per batch/pack': 'per_batch_pack',
    'per pack': 'per_pack',
    'per box': 'per_box',
}


def normalize_product_sale_types(apps, schema_editor):
    """Convert legacy sale_type values to slugified category keys."""
    Product = apps.get_model('inventory', 'Product')

    for product in Product.objects.all():
        current_value = (product.sale_type or '').strip().lower()
        mapped_value = SALE_TYPE_VALUE_MAP.get(current_value, current_value)
        if not mapped_value:
            continue
        if mapped_value != product.sale_type:
            product.sale_type = mapped_value
            product.save(update_fields=['sale_type'])


def reverse_normalize_product_sale_types(apps, schema_editor):
    """No reverse migration for canonicalization."""


class Migration(migrations.Migration):
    dependencies = [
        ('inventory', '0024_normalize_product_units_and_sale_types'),
    ]

    operations = [
        migrations.RunPython(normalize_product_sale_types, reverse_normalize_product_sale_types),
    ]
