from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('payroll', '0014_payrollperiod_branch'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='payslip',
            name='allowance',
        ),
    ]