from datetime import date, datetime
from decimal import Decimal

from django.test import TestCase

from attendance.models import DailyAttendance, MonthlyAttendanceSummary
from employees.models import StaffMember
from payroll.models import Payslip, PayrollPeriod
from payroll.views import get_payroll_report_rows
from attendance.views import can_import_attendance_for_month
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

    def test_payslip_counts_13_eligible_days_for_first_half_overtime(self):
        set_setting('payroll_default_rest_days', 4)
        staff = StaffMember.objects.create(
            first_name='Ariel',
            last_name='Dela Cruz',
            biometric_id='BIO-ARIEL',
            salary=30000,
            position=StaffMember.Position.RECEPTIONIST,
            is_active=True,
        )
        period = PayrollPeriod.objects.create(
            month=8,
            year=2026,
            period_type=PayrollPeriod.PeriodType.SEMI_FIRST,
        )

        payroll_dates = [date(2026, 8, day) for day in range(1, 16)]
        for attendance_date in payroll_dates:
            DailyAttendance.objects.create(
                staff=staff,
                attendance_date=attendance_date,
                morning_in=datetime.strptime('08:00', '%H:%M').time(),
                morning_out=datetime.strptime('12:00', '%H:%M').time(),
                afternoon_in=datetime.strptime('13:00', '%H:%M').time(),
                afternoon_out=datetime.strptime('17:00', '%H:%M').time(),
                check_in=datetime.strptime('08:00', '%H:%M').time(),
                check_out=datetime.strptime('17:00', '%H:%M').time(),
                ot_in=datetime.strptime('17:30', '%H:%M').time(),
                ot_out=datetime.strptime('19:30', '%H:%M').time(),
                ot_hours_calculated=Decimal('2'),
                is_present=True,
                status='PRESENT',
                four_punch_complete=True,
            )

        payslip = Payslip.objects.create(
            payroll_period=period,
            employee=staff,
            base_salary=Decimal('15000'),
        )

        payslip.generate_from_employee()

        self.assertEqual(payslip.overtime_hours, Decimal('26'))

    def test_payslip_uses_summary_when_daily_rows_lack_time_metadata(self):
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
        self.assertEqual(payslip.working_days, 13)
        self.assertEqual(payslip.days_absent, 13)
        self.assertEqual(payslip.rest_days_actual, 4)

    def test_payslip_treats_morning_only_time_as_absent_even_if_summary_shows_one_day(self):
        set_setting('payroll_default_rest_days', 4)
        staff = StaffMember.objects.create(
            first_name='Francis',
            last_name='Rosaros',
            biometric_id='BIO-FRANCIS',
            salary=30000,
            position=StaffMember.Position.RECEPTIONIST,
            is_active=True,
        )
        period = PayrollPeriod.objects.create(
            month=8,
            year=2026,
            period_type=PayrollPeriod.PeriodType.SEMI_SECOND,
        )
        MonthlyAttendanceSummary.objects.create(
            staff=staff,
            period_start=date(2026, 8, 16),
            period_end=date(2026, 8, 31),
            working_days=16,
            attendance_days=1,
            absence_days=15,
        )
        DailyAttendance.objects.create(
            staff=staff,
            attendance_date=date(2026, 8, 17),
            morning_in=datetime.strptime('08:26', '%H:%M').time(),
            morning_out=None,
            afternoon_in=None,
            afternoon_out=None,
            check_in=datetime.strptime('08:26', '%H:%M').time(),
            check_out=None,
            status='ABSENT',
            is_present=False,
            four_punch_complete=False,
        )

        payslip = Payslip.objects.create(
            payroll_period=period,
            employee=staff,
            base_salary=Decimal('15000'),
        )

        payslip.generate_from_employee()

        self.assertEqual(payslip.days_worked, 0)
        self.assertEqual(payslip.days_absent, payslip.working_days)

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

    def test_payslip_uses_summary_when_raw_rows_lack_time_metadata(self):
        set_setting('payroll_default_rest_days', 4)
        staff = StaffMember.objects.create(
            first_name='Dina',
            last_name='San Jose',
            biometric_id='BIO-DINA',
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
            overtime_hours=Decimal('5.50'),
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

        self.assertEqual(payslip.working_days, 13)
        self.assertEqual(payslip.days_worked, 0)
        self.assertEqual(payslip.days_absent, 13)
        self.assertEqual(payslip.overtime_hours, Decimal('5.50'))

    def test_payslip_uses_half_month_formula_when_no_attendance_data_exists(self):
        set_setting('payroll_default_rest_days', 4)
        staff = StaffMember.objects.create(
            first_name='Karl',
            last_name='NoData',
            biometric_id='BIO-KARL-NODATA',
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
            base_salary=Decimal('15000'),
        )

        payslip.generate_from_employee()

        self.assertEqual(period.get_period_start_end_dates(), (date(2026, 8, 1), date(2026, 8, 15)))
        self.assertEqual(payslip.working_days, 13)
        self.assertEqual(payslip.days_worked, 0)
        self.assertEqual(payslip.days_absent, 13)
        self.assertEqual(payslip.rest_days_actual, 4)

    def test_attendance_import_is_allowed_until_both_half_months_are_generated(self):
        PayrollPeriod.objects.create(
            month=8,
            year=2026,
            period_type=PayrollPeriod.PeriodType.SEMI_FIRST,
            status=PayrollPeriod.Status.GENERATED,
        )

        self.assertTrue(can_import_attendance_for_month(2026, 8))

        PayrollPeriod.objects.create(
            month=8,
            year=2026,
            period_type=PayrollPeriod.PeriodType.SEMI_SECOND,
            status=PayrollPeriod.Status.RELEASED,
        )

        self.assertFalse(can_import_attendance_for_month(2026, 8))

    def test_payslip_counts_full_second_half_days_when_raw_time_metadata_exists(self):
        set_setting('payroll_default_rest_days', 4)
        staff = StaffMember.objects.create(
            first_name='Carl Vincent',
            last_name='Sanchez',
            biometric_id='BIO-CARL',
            salary=30000,
            position=StaffMember.Position.RECEPTIONIST,
            is_active=True,
        )
        second_half = PayrollPeriod.objects.create(
            month=8,
            year=2026,
            period_type=PayrollPeriod.PeriodType.SEMI_SECOND,
        )

        for day in range(17, 32):
            DailyAttendance.objects.create(
                staff=staff,
                attendance_date=date(2026, 8, day),
                morning_in=datetime.strptime('07:30', '%H:%M').time(),
                morning_out=datetime.strptime('12:00', '%H:%M').time(),
                afternoon_in=datetime.strptime('13:00', '%H:%M').time(),
                afternoon_out=datetime.strptime('17:30', '%H:%M').time(),
                check_in=datetime.strptime('07:30', '%H:%M').time(),
                check_out=datetime.strptime('17:30', '%H:%M').time(),
                status='PRESENT',
                is_present=True,
                four_punch_complete=True,
            )

        payslip = Payslip.objects.create(
            payroll_period=second_half,
            employee=staff,
            base_salary=Decimal('15000'),
        )

        payslip.generate_from_employee()

        self.assertEqual(second_half.get_period_start_end_dates(), (date(2026, 8, 16), date(2026, 8, 31)))
        self.assertEqual(payslip.days_worked, 14)
        self.assertEqual(payslip.working_days, 14)
        self.assertEqual(payslip.days_absent, 0)

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
