from django.db import migrations, models
import django.db.models.deletion


def assign_single_branch_periods(apps, schema_editor):
    PayrollPeriod = apps.get_model('payroll', 'PayrollPeriod')
    for period in PayrollPeriod.objects.filter(branch__isnull=True):
        branch_ids = set(
            period.payslips.exclude(employee__branch_id__isnull=True).values_list(
                'employee__branch_id', flat=True
            )
        )
        if len(branch_ids) == 1:
            period.branch_id = branch_ids.pop()
            period.save(update_fields=['branch'])


class Migration(migrations.Migration):
    dependencies = [
        ('branches', '0006_branch_is_main_source'),
        ('payroll', '0013_payslip_monthly_attendance_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='payrollperiod',
            name='branch',
            field=models.ForeignKey(blank=True, help_text='Branch covered by this payroll period; blank means all branches.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='payroll_periods', to='branches.branch'),
        ),
        migrations.AlterUniqueTogether(
            name='payrollperiod',
            unique_together=set(),
        ),
        migrations.AddConstraint(
            model_name='payrollperiod',
            constraint=models.UniqueConstraint(fields=('month', 'year', 'branch'), name='unique_payroll_period_month_year_branch'),
        ),
        migrations.RunPython(assign_single_branch_periods, migrations.RunPython.noop),
    ]