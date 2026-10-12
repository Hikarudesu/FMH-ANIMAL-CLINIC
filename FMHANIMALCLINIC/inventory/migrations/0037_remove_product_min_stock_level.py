from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0036_remove_obsolete_product_unit_columns'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='product',
            name='min_stock_level',
        ),
    ]