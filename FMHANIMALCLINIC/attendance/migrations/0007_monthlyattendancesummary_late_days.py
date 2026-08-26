from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('attendance', '0006_monthlyattendancesummary'),
    ]

    operations = [
        migrations.AddField(
            model_name='monthlyattendancesummary',
            name='late_days',
            field=models.PositiveIntegerField(default=0),
        ),
    ]
