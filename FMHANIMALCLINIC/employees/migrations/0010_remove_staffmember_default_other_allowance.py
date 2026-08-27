from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('employees', '0009_staffmember_biometric_id'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='staffmember',
            name='default_other_allowance',
        ),
    ]