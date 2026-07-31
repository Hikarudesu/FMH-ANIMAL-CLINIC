# Generated manually for renaming BillableItem to Service

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0006_service_deleted_at_service_is_deleted'),
    ]

    operations = [
        migrations.RenameModel(
            old_name='BillableItem',
            new_name='Service',
        ),
    ]
