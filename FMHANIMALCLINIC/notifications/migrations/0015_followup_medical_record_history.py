import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('notifications', '0014_followup_expiration'),
    ]

    operations = [
        migrations.AlterField(
            model_name='followup',
            name='medical_record',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='follow_up_schedule',
                to='records.medicalrecord',
            ),
        ),
    ]
