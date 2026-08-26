from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('attendance', '0004_remove_biometricdevice_is_primary'),
    ]

    operations = [
        migrations.DeleteModel(
            name='AttendanceException',
        ),
    ]
