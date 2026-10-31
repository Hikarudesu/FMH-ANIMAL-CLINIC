from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0037_remove_product_min_stock_level'),
        ('pos', '0006_sale_guest_pet_name'),
    ]

    operations = [
        migrations.AddField(
            model_name='reservation',
            name='sale',
            field=models.ForeignKey(
                blank=True,
                help_text='POS sale created for reservation payment',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='product_reservation',
                to='pos.sale',
            ),
        ),
    ]
