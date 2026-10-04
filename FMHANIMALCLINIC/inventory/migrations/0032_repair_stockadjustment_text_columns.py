from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0031_stockadjustment_quantity_unit'),
    ]

    operations = [
        migrations.RunSQL(
            sql=(
                "ALTER TABLE inventory_stockadjustment "
                "ALTER COLUMN adjustment_type TYPE varchar(20), "
                "ALTER COLUMN reference TYPE varchar(50), "
                "ALTER COLUMN quantity_unit TYPE varchar(50), "
                "ALTER COLUMN reason TYPE varchar(255);"
            ),
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]