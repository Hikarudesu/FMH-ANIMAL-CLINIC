from datetime import date
from decimal import Decimal

from django.test import TestCase

from attendance.models import DailyAttendance, MonthlyAttendanceSummary
from employees.models import StaffMember
from payroll.models import Payslip, PayrollPeriod
from payroll.views import get_payroll_report_rows
from settings.utils import set_setting


class PayrollRulesTests(TestCase):
    def test_payroll_period_has_no_full_month_option(self):
        values = dict(PayrollPeriod.PeriodType.choices)
        self.assertNotIn('MONTHLY', values)
        self.assertEqual(PayrollPeriod.PeriodType.SEMI_FIRST, PayrollPeriod._meta.get_field('period_type').default)

    def test_default_overtime_and_rest_day_settings_are_available(self):
        set_setting('payroll_default_overtime_pay_per_hour', Decimal('120.00'))
        set_setting('payroll_default_rest_days', 5)

        self.assertEqual(Decimal('120.00'), Decimal(str(__import__('settings.utils', fromlist=['get_setting']).get_setting('payroll_default_overtime_pay_per_hour', 0))))
        self.assertEqual(5, int(__import__('settings.utils', fromlist=['get_setting']).get_setting('payroll_default_rest_days', 4)))

    def test_payslip_ignores_summary_working_days_when_daily_rows_are_incomplete(self):
        set_setting('payroll_default_rest_days', 4)
        staff = StaffMember.objects.create(
            first_name='Rejoy',
            last_name='Mendoza',
            biometric_id='BIO-REJOY',
            salary=30000,
            position=StaffMember.Position.RECEPTIONIST,
            is_active=True,
        )
        period = PayrollPeriod.objects.create(
            month=8,
            year=2026,
            period_type=PayrollPeriod.PeriodType.SEMI_FIRST,
        )
        MonthlyAttendanceSummary.objects.create(
            staff=staff,
            period_start=date(2026, 8, 1),
            period_end=date(2026, 8, 15),
            working_days=27,
            attendance_days=0,
            absence_days=15,
        )
        DailyAttendance.objects.create(
            staff=staff,
            attendance_date=date(2026, 8, 4),
            check_in=None,
            check_out=None,
            status='ABSENT',
            is_present=False,
        )
        DailyAttendance.objects.create(
            staff=staff,
            attendance_date=date(2026, 8, 5),
            check_in=None,
            check_out=None,
            status='ABSENT',
            is_present=False,
        )

        payslip = Payslip.objects.create(
            payroll_period=period,
            employee=staff,
            base_salary=Decimal('15000'),
        )

        payslip.generate_from_employee()

        self.assertEqual(payslip.days_worked, 0)
        self.assertEqual(payslip.working_days, 0)
        self.assertEqual(payslip.days_absent, 2)
        self.assertEqual(payslip.rest_days_actual, 4)

    def test_payslip_uses_summary_working_days_and_zero_worked_when_no_time_metadata_exists(self):
        set_setting('payroll_default_rest_days', 4)
        staff = StaffMember.objects.create(
            first_name='Lena',
            last_name='Ramos',
            biometric_id='BIO-LENA',
            salary=30000,
            position=StaffMember.Position.RECEPTIONIST,
            is_active=True,
        )
        period = PayrollPeriod.objects.create(
            month=8,
            year=2026,
            period_type=PayrollPeriod.PeriodType.SEMI_FIRST,
        )
        MonthlyAttendanceSummary.objects.create(
            staff=staff,
            period_start=date(2026, 8, 1),
            period_end=date(2026, 8, 15),
            working_days=31,
            attendance_days=0,
            absence_days=30,
        )

        payslip = Payslip.objects.create(
            payroll_period=period,
            employee=staff,
            base_salary=Decimal('15000'),
        )

        payslip.generate_from_employee()

        self.assertEqual(payslip.working_days, 13)
        self.assertEqual(payslip.days_worked, 0)
        self.assertEqual(payslip.days_absent, 13)
        self.assertEqual(payslip.rest_days_actual, 4)

    def test_payslip_scales_summary_values_for_half_periods(self):
        set_setting('payroll_default_rest_days', 4)
        staff = StaffMember.objects.create(
            first_name='Mia',
            last_name='Valdez',
            biometric_id='BIO-MIA',
            salary=30000,
            position=StaffMember.Position.RECEPTIONIST,
            is_active=True,
        )
        first_half = PayrollPeriod.objects.create(
            month=8,
            year=2026,
            period_type=PayrollPeriod.PeriodType.SEMI_FIRST,
        )
        second_half = PayrollPeriod.objects.create(
            month=8,
            year=2026,
            period_type=PayrollPeriod.PeriodType.SEMI_SECOND,
        )
        MonthlyAttendanceSummary.objects.create(
            staff=staff,
            period_start=date(2026, 8, 1),
            period_end=date(2026, 8, 31),
            working_days=31,
            attendance_days=0,
            absence_days=30,
        )

        first_payslip = Payslip.objects.create(
            payroll_period=first_half,
            employee=staff,
            base_salary=Decimal('15000'),
        )
        first_payslip.generate_from_employee()

        second_payslip = Payslip.objects.create(
            payroll_period=second_half,
            employee=staff,
            base_salary=Decimal('15000'),
        )
        second_payslip.generate_from_employee()

        self.assertEqual(first_payslip.working_days, 13)
        self.assertEqual(first_payslip.days_absent, 13)
        self.assertEqual(second_payslip.working_days, 14)
        self.assertEqual(second_payslip.days_absent, 14)
        self.assertEqual(second_payslip.rest_days_actual, 4)

    def test_payslip_applies_default_absent_deduction_on_generation(self):
        set_setting('payroll_default_rest_days', 4)
        set_setting('payroll_default_absent_deduction', 150)

        staff = StaffMember.objects.create(
            first_name='Ari',
            last_name='Santos',
            biometric_id='BIO-ARI',
            salary=30000,
            position=StaffMember.Position.RECEPTIONIST,
            is_active=True,
        )
        period = PayrollPeriod.objects.create(
            month=8,
            year=2026,
            period_type=PayrollPeriod.PeriodType.SEMI_FIRST,
        )
        MonthlyAttendanceSummary.objects.create(
            staff=staff,
            period_start=date(2026, 8, 1),
            period_end=date(2026, 8, 15),
            working_days=31,
            attendance_days=0,
            absence_days=30,
        )

        payslip = Payslip.objects.create(
            payroll_period=period,
            employee=staff,
            base_salary=Decimal('15000'),
        )

        payslip.generate_from_employee()

        self.assertEqual(payslip.days_absent, 13)
        self.assertEqual(payslip.absent_deduction, Decimal('1950.00'))

    def test_report_allowances_include_all_earnings(self):
        staff = StaffMember.objects.create(
            first_name='Noel',
            last_name='Fernandez',
            biometric_id='BIO-NOEL',
            salary=30000,
            position=StaffMember.Position.RECEPTIONIST,
            is_active=True,
        )
        period = PayrollPeriod.objects.create(
            month=8,
            year=2026,
            period_type=PayrollPeriod.PeriodType.SEMI_FIRST,
        )
        payslip = Payslip.objects.create(
            payroll_period=period,
            employee=staff,
            base_salary=Decimal('15000.00'),
            overtime_pay=Decimal('250.00'),
            holiday_pay=Decimal('500.00'),
            bonus=Decimal('350.00'),
            staff_allowance=Decimal('2000.00'),
            thirteenth_month_pay=Decimal('1500.00'),
            net_pay=Decimal('19600.00'),
        )
        payslip.calculate()
        payslip.save()

        rows, total_net = get_payroll_report_rows(period)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['allowances'], Decimal('4600.00'))
        self.assertEqual(total_net, Decimal('19600.00'))
