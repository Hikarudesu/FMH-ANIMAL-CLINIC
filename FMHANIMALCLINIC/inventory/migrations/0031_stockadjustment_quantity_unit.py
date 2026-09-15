from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0030_align_product_units_to_specific_options'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql=(
                        "ALTER TABLE inventory_stockadjustment "
                        "ADD COLUMN IF NOT EXISTS quantity_unit varchar(50) "
                        "NOT NULL DEFAULT 'piece';"
                    ),
                    reverse_sql=(
                        "ALTER TABLE inventory_stockadjustment "
                        "DROP COLUMN IF EXISTS quantity_unit;"
                    ),
                ),
            ],
            state_operations=[
                migrations.AddField(
                    model_name='stockadjustment',
                    name='quantity_unit',
                    field=models.CharField(
                        default='piece',
                        help_text='Unit of measurement for the adjusted quantity.',
                        max_length=50,
                    ),
                ),
            ],
        ),
    ]
