from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0035_relax_legacy_inventory_unit_columns'),
    ]

    operations = [
        migrations.RunSQL(
            sql=(
                "ALTER TABLE inventory_product "
                "DROP COLUMN IF EXISTS base_unit, "
                "DROP COLUMN IF EXISTS base_units_per_sale_unit, "
                "DROP COLUMN IF EXISTS base_units_per_stock_unit, "
                "DROP COLUMN IF EXISTS stock_base_quantity, "
                "DROP COLUMN IF EXISTS use_unit_conversion;"
            ),
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
