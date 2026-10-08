from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0033_relax_legacy_base_unit_column'),
    ]

    operations = [
        migrations.RunSQL(
            sql=(
                "DO $$ BEGIN "
                "IF EXISTS (SELECT 1 FROM information_schema.columns "
                "WHERE table_schema = current_schema() "
                "AND table_name = 'inventory_product' "
                "AND column_name = 'base_units_per_sale_unit') THEN "
                "ALTER TABLE inventory_product "
                "ALTER COLUMN base_units_per_sale_unit DROP NOT NULL; "
                "END IF; END $$;"
            ),
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
