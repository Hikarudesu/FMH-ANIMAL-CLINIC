from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('notifications', '0006_alter_notification_notification_type'),
    ]

    operations = [
        migrations.AddField(
            model_name='notification',
            name='module_context',
            field=models.CharField(
                choices=[
                    ('appointments', 'Appointments'),
                    ('patients', 'Patients'),
                    ('medical_records', 'Medical Records'),
                    ('ai_diagnostics', 'AI Diagnostics'),
                    ('inventory', 'Inventory'),
                    ('soa', 'Statement of Account'),
                    ('notifications', 'Notifications'),
                    ('general', 'General'),
                ],
                default='general',
                help_text='Module scope used for RBAC filtering.',
                max_length=30,
            ),
        ),
    ]
