from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('attendance', '0007_monthlyattendancesummary_late_days'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='attendancelog',
            name='mapping',
        ),
        migrations.DeleteModel(
            name='StaffBiometricMapping',
        ),
    ]
