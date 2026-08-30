# Generated migration to add semi-monthly payroll support

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('payroll', '0014_payrollperiod_branch'),
    ]

    operations = [
        # Add period_type field to PayrollPeriod
        migrations.AddField(
            model_name='payrollperiod',
            name='period_type',
            field=models.CharField(
                choices=[
                    ('MONTHLY', 'Full Month'),
                    ('SEMI_FIRST', '1st - 15th (First Half)'),
                    ('SEMI_SECOND', '16th - End of Month (Second Half)')
                ],
                default='MONTHLY',
                help_text='Select full month, first half (1-15), or second half (16-EOMonth)',
                max_length=20
            ),
        ),
        
        # Add edited_at field to PayrollPeriod
        migrations.AddField(
            model_name='payrollperiod',
            name='edited_at',
            field=models.DateTimeField(
                blank=True,
                null=True,
                help_text='When payslips were last edited'
            ),
        ),
        
        # Add EDITED status choice to PayrollPeriod status field
        migrations.AlterField(
            model_name='payrollperiod',
            name='status',
            field=models.CharField(
                choices=[
                    ('DRAFT', 'Draft'),
                    ('EDITED', 'Payslips Edited'),
                    ('GENERATED', 'Generated'),
                    ('RELEASED', 'Released')
                ],
                default='DRAFT',
                max_length=20
            ),
        ),
        
        # Remove old unique constraint
        migrations.RemoveConstraint(
            model_name='payrollperiod',
            name='unique_payroll_period_month_year_branch',
        ),
        
        # Add new unique constraint with period_type
        migrations.AddConstraint(
            model_name='payrollperiod',
            constraint=models.UniqueConstraint(
                fields=['month', 'year', 'period_type', 'branch'],
                name='unique_payroll_period_by_type_and_branch'
            ),
        ),
        
        # Add new index for period_type
        migrations.AddIndex(
            model_name='payrollperiod',
            index=models.Index(fields=['period_type'], name='payroll_pay_period_idx'),
        ),
    ]
