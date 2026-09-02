from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('payroll', '0020_alter_payrollperiod_period_type'),
    ]

    operations = [
        migrations.AddConstraint(
            model_name='payslipemaillog',
            constraint=models.UniqueConstraint(
                condition=models.Q(status='SENT'),
                fields=('payslip', 'recipient_email'),
                name='unique_successful_payslip_email',
            ),
        ),
    ]