from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0011_alter_customerstatement_customer'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='service',
            name='branch',
        ),
    ]
