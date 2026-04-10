from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('pos', '0005_sale_soa_data'),
        ('billing', '0009_customerstatement_boarding_description_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='customerstatement',
            name='sale',
            field=models.ForeignKey(
                blank=True,
                help_text='Linked POS sale that generated this statement.',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='customer_statements',
                to='pos.sale',
            ),
        ),
    ]
