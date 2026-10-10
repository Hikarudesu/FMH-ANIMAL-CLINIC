from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('appointments', '0015_alter_appointment_source'),
        ('records', '0018_medicalfile_laboratory_type'),
    ]

    operations = [
        migrations.AddField(
            model_name='recordentry',
            name='appointment',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='record_entries',
                to='appointments.appointment',
            ),
        ),
    ]
