from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('payroll', '0012_payslip_custom_deductions_total_payslipdeduction'),
    ]

    operations = [
        migrations.AddField(
            model_name='payslip',
            name='working_days',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='payslip',
            name='sick_hours',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=7),
        ),
        migrations.AddField(
            model_name='payslip',
            name='leave_hours',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=7),
        ),
        migrations.AddField(
            model_name='payslip',
            name='daily_salary',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=12),
        ),
    ]
