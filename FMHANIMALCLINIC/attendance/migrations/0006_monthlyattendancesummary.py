from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('attendance', '0005_delete_attendanceexception'),
    ]

    operations = [
        migrations.CreateModel(
            name='MonthlyAttendanceSummary',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('period_start', models.DateField()),
                ('period_end', models.DateField()),
                ('working_days', models.PositiveIntegerField(default=0)),
                ('attendance_days', models.PositiveIntegerField(default=0)),
                ('absence_days', models.PositiveIntegerField(default=0)),
                ('overtime_hours', models.DecimalField(decimal_places=2, default=0, max_digits=7)),
                ('sick_hours', models.DecimalField(decimal_places=2, default=0, max_digits=7)),
                ('leave_hours', models.DecimalField(decimal_places=2, default=0, max_digits=7)),
                ('daily_salary', models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('overtime_pay', models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('allowances', models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('charges', models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('real_pay', models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('imported_at', models.DateTimeField(auto_now=True)),
                ('staff', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='monthly_attendance_summaries', to='employees.staffmember')),
            ],
            options={
                'ordering': ['-period_start', 'staff'],
                'constraints': [models.UniqueConstraint(fields=('staff', 'period_start', 'period_end'), name='unique_staff_attendance_month')],
            },
        ),
    ]
