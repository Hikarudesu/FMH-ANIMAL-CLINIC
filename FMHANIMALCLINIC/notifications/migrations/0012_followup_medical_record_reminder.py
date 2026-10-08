from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('notifications', '0011_followup_email_tracking'),
        ('records', '0017_rename_records_med_medical_7b8ea0_idx_records_med_medical_18ee7c_idx_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='followup',
            name='appointment',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='follow_ups',
                to='appointments.appointment',
            ),
        ),
        migrations.AddField(
            model_name='followup',
            name='medical_record',
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='follow_up_schedule',
                to='records.medicalrecord',
            ),
        ),
        migrations.AddField(
            model_name='followup',
            name='reminder_email_sent_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
