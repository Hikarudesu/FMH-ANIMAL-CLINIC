from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0012_remove_service_branch'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='service',
            name='tax_rate',
        ),
    ]