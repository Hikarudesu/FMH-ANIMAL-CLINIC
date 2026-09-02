import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(
            name='ScheduledReport',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=150)),
                ('frequency', models.CharField(choices=[('DAILY', 'Daily'), ('WEEKLY', 'Weekly'), ('MONTHLY', 'Monthly')], default='MONTHLY', max_length=10)),
                ('recipients', models.TextField(help_text='Comma-separated email addresses.')),
                ('is_active', models.BooleanField(default=True)),
                ('next_run_at', models.DateTimeField()),
                ('last_run_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('branch', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='branches.branch')),
                ('created_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='ScheduledReportDelivery',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('period_key', models.CharField(max_length=30)),
                ('recipients', models.TextField()),
                ('status', models.CharField(choices=[('SENT', 'Sent'), ('FAILED', 'Failed')], max_length=20)),
                ('error_message', models.TextField(blank=True)),
                ('sent_at', models.DateTimeField(auto_now_add=True)),
                ('report', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='deliveries', to='reports.scheduledreport')),
            ],
            options={'constraints': [models.UniqueConstraint(fields=('report', 'period_key'), name='unique_report_period_delivery')]},
        ),
    ]