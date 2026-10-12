from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0047_grant_clinical_staff_patient_transfer_permissions'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='inactive_reason',
            field=models.TextField(blank=True),
        ),
    ]