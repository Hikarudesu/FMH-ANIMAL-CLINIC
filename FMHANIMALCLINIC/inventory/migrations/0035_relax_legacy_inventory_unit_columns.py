from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0034_relax_legacy_base_units_per_sale_unit'),
    ]

    operations = [
        migrations.RunSQL(
            sql=(
                "DO $$ DECLARE legacy_column text; BEGIN "
                "FOREACH legacy_column IN ARRAY ARRAY["
                "'base_unit', "
                "'base_units_per_sale_unit', "
                "'base_units_per_stock_unit'"
                "] LOOP "
                "IF EXISTS (SELECT 1 FROM information_schema.columns "
                "WHERE table_schema = current_schema() "
                "AND table_name = 'inventory_product' "
                "AND column_name = legacy_column) THEN "
                "EXECUTE format('ALTER TABLE inventory_product ALTER COLUMN %I DROP NOT NULL', legacy_column); "
                "END IF; END LOOP; END $$;"
            ),
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
