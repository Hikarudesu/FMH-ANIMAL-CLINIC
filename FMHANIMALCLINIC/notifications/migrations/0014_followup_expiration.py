from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('notifications', '0013_followup_booked_appointment'),
    ]

    operations = [
        migrations.AddField(
            model_name='followup',
            name='is_expired',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='followup',
            name='expiration_reason',
            field=models.TextField(blank=True),
        ),
    ]
