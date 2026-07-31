"""Normalize existing product unit and sale type values."""

from django.db import migrations


SALE_TYPE_KEYWORDS = {
    'piece': 'piece',
    'per piece': 'piece',
    'batch': 'batch',
    'per batch/pack': 'batch',
    'per pack': 'batch',
    'per box': 'batch',
}


def normalize_product_units_and_sale_types(apps, schema_editor):
    """Convert existing inventory rows to canonical lowercase values."""
    Product = apps.get_model('inventory', 'Product')

    for product in Product.objects.all():
        unit_value = (product.unit_of_measurement or '').strip().lower()
        if unit_value:
            product.unit_of_measurement = unit_value

        sale_value = (product.sale_type or '').strip().lower()
        normalized_sale_type = SALE_TYPE_KEYWORDS.get(sale_value)
        if not normalized_sale_type:
            normalized_sale_type = SALE_TYPE_KEYWORDS.get((product.sale_type or '').strip().lower(), 'piece')
        product.sale_type = normalized_sale_type
        product.save(update_fields=['unit_of_measurement', 'sale_type'])


def reverse_normalize_product_units_and_sale_types(apps, schema_editor):
    """No reverse migration for canonicalization."""


class Migration(migrations.Migration):
    dependencies = [
        ('inventory', '0023_alter_product_sale_type'),
    ]

    operations = [
        migrations.RunPython(normalize_product_units_and_sale_types, reverse_normalize_product_units_and_sale_types),
    ]
