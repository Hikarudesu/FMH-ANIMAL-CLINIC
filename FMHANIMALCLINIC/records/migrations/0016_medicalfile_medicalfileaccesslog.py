import django.db.models.deletion
import records.models
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('records', '0015_remove_lab_results_fields'),
    ]

    operations = [
        migrations.CreateModel(
            name='MedicalFile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('file', models.FileField(upload_to='records.models.medical_file_upload_path', validators=[records.models.validate_medical_file])),
                ('original_name', models.CharField(max_length=255)),
                ('file_type', models.CharField(choices=[('LAB', 'Laboratory Result'), ('IMAGING', 'Medical Imaging'), ('OTHER', 'Other Medical Document')], default='OTHER', max_length=20)),
                ('sha256', models.CharField(editable=False, max_length=64)),
                ('uploaded_at', models.DateTimeField(auto_now_add=True)),
                ('record', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='medical_files', to='records.medicalrecord')),
                ('uploaded_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-uploaded_at']},
        ),
        migrations.CreateModel(
            name='MedicalFileAccessLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('action', models.CharField(choices=[('UPLOAD', 'Upload'), ('DOWNLOAD', 'Download'), ('DELETE', 'Delete'), ('DENIED', 'Denied')], max_length=20)),
                ('success', models.BooleanField(default=False)),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('detail', models.CharField(blank=True, max_length=255)),
                ('medical_file', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='access_logs', to='records.medicalfile')),
                ('user', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-created_at'], 'indexes': [models.Index(fields=['medical_file', 'created_at'], name='records_med_medical_7b8ea0_idx')]},
        ),
    ]