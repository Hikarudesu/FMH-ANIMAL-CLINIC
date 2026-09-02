from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('appointments', '0015_alter_appointment_source'),
    ]

    operations = [
        migrations.AddField(
            model_name='appointment',
            name='reminder_1_sent_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='appointment',
            name='reminder_2_sent_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]