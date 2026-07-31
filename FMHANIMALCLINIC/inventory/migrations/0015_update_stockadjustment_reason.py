# Generated manually for reason field constraint and default

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0014_product_inventory_p_branch__d8816f_idx_and_more'),
    ]

    operations = [
        # First, set all NULL values to the default
        migrations.RunSQL(
            "UPDATE inventory_stockadjustment SET reason = 'Manual adjustment' WHERE reason IS NULL;",
            reverse_sql="UPDATE inventory_stockadjustment SET reason = NULL WHERE reason = 'Manual adjustment' AND id IN (SELECT id FROM inventory_stockadjustment WHERE reason IS NULL);",
        ),
        # Then, add the NOT NULL constraint and default
        migrations.AlterField(
            model_name='stockadjustment',
            name='reason',
            field=models.CharField(
                default='Manual adjustment',
                max_length=255,
                help_text='Reason for this adjustment (required)'
            ),
        ),
    ]
