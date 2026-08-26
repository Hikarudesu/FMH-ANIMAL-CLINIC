from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0035_add_attendance_module'),
        ('attendance', '0008_remove_staff_biometric_mapping'),
    ]

    operations = [
        migrations.AddField(
            model_name='monthlyattendancesummary',
            name='approved_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='monthlyattendancesummary',
            name='approved_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='approved_monthly_attendance', to='accounts.user'),
        ),
        migrations.AddField(
            model_name='monthlyattendancesummary',
            name='review_status',
            field=models.CharField(choices=[('IMPORTED', 'Imported'), ('APPROVED', 'Approved'), ('LOCKED', 'Locked')], default='IMPORTED', max_length=20),
        ),
        migrations.AddField(
            model_name='monthlyattendancesummary',
            name='source_filename',
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name='monthlyattendancesummary',
            name='uploaded_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='monthly_attendance_uploads', to='accounts.user'),
        ),
    ]
