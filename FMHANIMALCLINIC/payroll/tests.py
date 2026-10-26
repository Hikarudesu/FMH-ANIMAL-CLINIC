from datetime import date, datetime
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from attendance.models import DailyAttendance, MonthlyAttendanceSummary
from attendance.services import AttendanceImportService
from employees.models import StaffMember
from payroll.models import Payslip, PayrollAuditLog, PayrollPeriod
from payroll.views import get_payroll_report_rows
from attendance.views import can_import_attendance_for_month
from settings.utils import set_setting


class PayrollPeriodDeletionTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser(
            username='payroll-delete-admin',
            email='payroll-delete-admin@example.com',
            password='test-password',
        )
        self.client.force_login(self.admin)

    @patch('payroll.views.timezone.localdate', return_value=date(2026, 10, 15))
    def test_cannot_delete_payroll_period_from_past_month(self, _mock_today):
        period = PayrollPeriod.objects.create(
            month=9,
            year=2026,
            period_type=PayrollPeriod.PeriodType.SEMI_FIRST,
            status=PayrollPeriod.Status.GENERATED,
        )

        response = self.client.post(reverse('payroll:delete_period', args=[period.pk]))

        self.assertRedirects(response, reverse('payroll:requests'))
        self.assertTrue(PayrollPeriod.objects.filter(pk=period.pk).exists())

        list_response = self.client.get(reverse('payroll:requests'))
        self.assertContains(list_response, 'Past-month payroll periods cannot be deleted.')

    @patch('payroll.views.timezone.localdate', return_value=date(2026, 10, 15))
    def test_can_delete_payroll_period_from_current_month(self, _mock_today):
        period = PayrollPeriod.objects.create(
            month=10,
            year=2026,
            period_type=PayrollPeriod.PeriodType.SEMI_FIRST,
            status=PayrollPeriod.Status.GENERATED,
        )

        response = self.client.post(reverse('payroll:delete_period', args=[period.pk]))

        self.assertRedirects(response, reverse('payroll:requests'))
        self.assertFalse(PayrollPeriod.objects.filter(pk=period.pk).exists())


class PayrollAuditLogTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser(
            username='payroll-audit-admin',
            email='payroll-audit-admin@example.com',
            password='test-password',
        )
        self.client.force_login(self.admin)

    def test_action_filter_retains_actions_without_matches(self):
        PayrollAuditLog.objects.create(
            user=self.admin,
            action_type=PayrollAuditLog.ActionType.PERIOD_GENERATED,
            description='Generated a payroll period',
        )

        response = self.client.get(
            reverse('payroll:audit_log'),
            {'action_type': PayrollAuditLog.ActionType.PERIOD_GENERATED},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'value="PAYSLIP_SENT"')

    def test_creating_payroll_period_writes_audit_record_with_ip(self):
        response = self.client.get(
            reverse('payroll:generate'),
            {
                'load': '1',
                'month': '10',
                'year': '2099',
                'period_type': PayrollPeriod.PeriodType.SEMI_FIRST,
                'branch': 'ALL',
            },
            REMOTE_ADDR='203.0.113.18',
        )

        period = PayrollPeriod.objects.get(year=2099, month=10)
        log = PayrollAuditLog.objects.get(
            action_type=PayrollAuditLog.ActionType.PERIOD_CREATED,
            payroll_period=period,
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(log.user, self.admin)
        self.assertEqual(log.ip_address, '203.0.113.18')
        self.assertEqual(log.metadata['branch'], 'All Branches')

    def test_detail_renders_nested_metadata_and_ip_address(self):
        log = PayrollAuditLog.objects.create(
            user=self.admin,
            action_type=PayrollAuditLog.ActionType.PERIOD_DELETED,
            description='Deleted September payroll',
            metadata={
                'period_name': 'September 2026 - First Half',
                'period_id': 42,
                'deleted_payslip': {'employee_name': 'Ana Santos', 'net_pay': '25000.00'},
            },
            ip_address='203.0.113.42',
        )

        response = self.client.get(reverse('payroll:audit_log_detail', args=[log.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'September 2026 - First Half')
        self.assertContains(response, 'Ana Santos')
        self.assertContains(response, '25000.00')
        self.assertContains(response, '203.0.113.42')


class PayslipEditTests(TestCase):
    def test_printed_payslip_shows_paid_leave_and_reduced_absences(self):
        admin = get_user_model().objects.create_superuser(
            username='payslip-print-admin',
            email='payslip-print-admin@example.com',
            password='test-password',
        )
        self.client.force_login(admin)
        staff = StaffMember.objects.create(
            first_name='Nina',
            last_name='Garcia',
            biometric_id='BIO-NINA',
            salary=30000,
            position=StaffMember.Position.RECEPTIONIST,
            is_active=True,
            user=admin,
        )
        period = PayrollPeriod.objects.create(
            month=4,
            year=2099,
            period_type=PayrollPeriod.PeriodType.SEMI_FIRST,
        )
        payslip = Payslip.objects.create(
            payroll_period=period,
            employee=staff,
            base_salary=Decimal('15000'),
            days_absent=3,
            paid_leave_days=Decimal('1'),
        )

        response = self.client.get(reverse('payroll:payslip_print', args=[payslip.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['effective_absence_days'], 2)
        self.assertContains(response, '<span class="val">2</span>')
        self.assertContains(response, 'Paid Leave Days')
        self.assertContains(response, '<span class="val">1</span>')

        from django.template.loader import render_to_string
        email_html = render_to_string('payroll/payslip_email_pdf.html', {
            'payslip': payslip,
            'effective_absence_days': response.context['effective_absence_days'],
            'ledger_rows': [],
            'logo_data_uri': '',
        })
        self.assertIn('Days Absent</span><span class="info-value">2</span>', email_html)
        self.assertIn('Paid Leave Days</span><span class="info-value">1</span>', email_html)

    def test_overtime_setting_is_shown_when_payslip_has_no_saved_overtime_pay(self):
        admin = get_user_model().objects.create_superuser(
            username='payslip-rate-admin',
            email='payslip-rate-admin@example.com',
            password='test-password',
        )
        self.client.force_login(admin)
        staff = StaffMember.objects.create(
            first_name='Tina',
            last_name='Lopez',
            biometric_id='BIO-TINA',
            salary=30000,
            position=StaffMember.Position.RECEPTIONIST,
            is_active=True,
            user=admin,
        )
        period = PayrollPeriod.objects.create(
            month=3,
            year=2099,
            period_type=PayrollPeriod.PeriodType.SEMI_FIRST,
        )
        payslip = Payslip.objects.create(
            payroll_period=period,
            employee=staff,
            base_salary=Decimal('15000'),
            overtime_pay=Decimal('0'),
            paid_leave_days=Decimal('2.00'),
        )
        set_setting('payroll_default_overtime_pay_per_hour', Decimal('187.50'))

        response = self.client.get(reverse('payroll:payslip_edit', args=[payslip.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Overtime Rate (₱/Hour)')
        self.assertContains(response, 'value="187.50" readonly')
        self.assertContains(response, 'name="overtime_pay" class="currency-input" value="0.00" readonly')
        self.assertContains(response, 'name="paid_leave_days" value="2"')

    def test_paid_leave_persists_when_monthly_attendance_summary_is_missing(self):
        admin = get_user_model().objects.create_superuser(
            username='payslip-no-summary-admin',
            email='payslip-no-summary-admin@example.com',
            password='test-password',
        )
        self.client.force_login(admin)
        staff = StaffMember.objects.create(
            first_name='Lina',
            last_name='Cruz',
            biometric_id='BIO-LINA',
            salary=30000,
            position=StaffMember.Position.RECEPTIONIST,
            is_active=True,
            user=admin,
        )
        period = PayrollPeriod.objects.create(
            month=2,
            year=2099,
            period_type=PayrollPeriod.PeriodType.SEMI_FIRST,
        )
        payslip = Payslip.objects.create(
            payroll_period=period,
            employee=staff,
            base_salary=Decimal('15000'),
        )

        response = self.client.post(
            reverse('payroll:payslip_edit', args=[payslip.pk]),
            {
                'paid_leave_days': '1',
                'paid_leave_type': 'Sick Leave',
                'rest_days_mandatory': '4',
                'overtime_hours': '0',
                'overtime_pay': '0',
                'holiday_pay': '0',
                'bonus': '0',
                'staff_allowance': '0',
                'sss': '0',
                'philhealth': '0',
                'pagibig': '0',
                'cash_advance': '0',
                'late_deduction': '0',
                'other_deductions': '0',
                'sick_leave_days': '0',
                'regular_leave_days': '0',
                'notes': '',
            },
        )

        self.assertEqual(response.status_code, 302)
        payslip.refresh_from_db()
        self.assertEqual(payslip.paid_leave_days, Decimal('1'))

        edit_response = self.client.get(reverse('payroll:payslip_edit', args=[payslip.pk]))

        self.assertEqual(edit_response.status_code, 200)
        self.assertEqual(edit_response.context['payslip'].paid_leave_days, Decimal('1'))
        self.assertEqual(
            edit_response.context['effective_absence_days'],
            max(0, payslip.days_absent - 1),
        )
        self.assertRegex(
            edit_response.content.decode(),
            r'name="paid_leave_days" value="1(?:\.0+)?"',
        )

    def test_saving_paid_leave_reduces_absence_deduction_and_net_pay(self):
        set_setting('payroll_default_overtime_pay_per_hour', Decimal('100.00'))
        admin = get_user_model().objects.create_superuser(
            username='payslip-edit-admin',
            email='payslip-edit-admin@example.com',
            password='test-password',
        )
        self.client.force_login(admin)
        staff = StaffMember.objects.create(
            first_name='Mina',
            last_name='Reyes',
            biometric_id='BIO-MINA',
            salary=30000,
            position=StaffMember.Position.RECEPTIONIST,
            is_active=True,
            user=admin,
        )
        period = PayrollPeriod.objects.create(
            month=1,
            year=2099,
            period_type=PayrollPeriod.PeriodType.SEMI_FIRST,
        )
        from attendance.calculation_engine import WorkingDaysCalculator
        working_days = WorkingDaysCalculator.calculate_required_working_days(
            period.year, period.month, period.period_type, 4
        )
        period_start, period_end = period.get_period_start_end_dates()
        MonthlyAttendanceSummary.objects.create(
            staff=staff,
            period_start=period_start,
            period_end=period_end,
            working_days=working_days,
            attendance_days=working_days - 3,
            absence_days=3,
        )
        payslip = Payslip.objects.create(
            payroll_period=period,
            employee=staff,
            base_salary=Decimal('15000'),
            staff_allowance=Decimal('0'),
        )

        response = self.client.post(
            reverse('payroll:payslip_edit', args=[payslip.pk]),
            {
                'working_days': working_days,
                'days_worked': working_days,
                'days_absent': 0,
                'paid_leave_days': 1,
                'paid_leave_type': 'Sick Leave',
                'rest_days_mandatory': 4,
                'overtime_hours': '2',
                'overtime_pay': '999.00',
                'holiday_pay': '120.00',
                'bonus': '250.00',
                'staff_allowance': '500.00',
                'sss': 0,
                'philhealth': 0,
                'pagibig': 0,
                'cash_advance': 0,
                'late_deduction': 0,
                'other_deductions': 0,
                'sick_leave_days': 0,
                'regular_leave_days': 0,
                'deduction_reason[]': ['Uniform'],
                'deduction_amount[]': ['75.00'],
                'notes': '',
            },
        )

        payslip.refresh_from_db()
        expected_absence_deduction = (
            Decimal('15000') / Decimal(str(working_days)) * Decimal('2')
        ).quantize(Decimal('0.01'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(payslip.days_absent, 3)
        self.assertEqual(payslip.paid_leave_days, Decimal('1'))
        self.assertEqual(payslip.overtime_pay, Decimal('200.00'))
        self.assertEqual(payslip.holiday_pay, Decimal('120.00'))
        self.assertEqual(payslip.bonus, Decimal('250.00'))
        self.assertEqual(payslip.staff_allowance, Decimal('500.00'))
        self.assertEqual(payslip.absent_deduction, expected_absence_deduction)
        self.assertGreaterEqual(payslip.total_deductions, payslip.absent_deduction)
        self.assertEqual(payslip.net_pay, payslip.gross_pay - payslip.total_deductions)

        edit_response = self.client.get(reverse('payroll:payslip_edit', args=[payslip.pk]))
        self.assertEqual(edit_response.context['effective_absence_days'], 2)
        self.assertContains(edit_response, 'id="daysAbsentInput" value="2"')
        self.assertRegex(
            edit_response.content.decode(),
            r'name="paid_leave_days" value="1(?:\.0+)?"',
        )
        self.assertContains(edit_response, 'name="overtime_pay" class="currency-input" value="200.00" readonly')
        self.assertContains(edit_response, 'name="holiday_pay" class="currency-input" value="120.00"')
        self.assertContains(edit_response, 'name="bonus" class="currency-input" value="250.00"')
        self.assertContains(edit_response, 'name="staff_allowance" class="currency-input" value="500.00"')
        self.assertContains(edit_response, 'name="deduction_amount[]" class="currency-input" value="75.00"')


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

    def test_generated_payslip_uses_configured_rest_days(self):
        set_setting('payroll_default_rest_days', 6)
        staff = StaffMember.objects.create(
            first_name='Rest Day',
            last_name='Configured',
            biometric_id='BIO-REST-CONFIGURED',
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

        self.assertEqual(payslip.rest_days_mandatory, 6)
        self.assertEqual(payslip.working_days, 12)

    def test_payslip_counts_13_eligible_days_for_first_half_overtime(self):
        set_setting('payroll_default_rest_days', 4)
        set_setting('payroll_default_overtime_pay_per_hour', Decimal('150.00'))
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
        self.assertEqual(payslip.overtime_pay, Decimal('3900.00'))

    def test_uploaded_overtime_hours_use_configured_payslip_rate(self):
        set_setting('payroll_default_rest_days', 4)
        set_setting('payroll_default_overtime_pay_per_hour', Decimal('175.00'))
        staff = StaffMember.objects.create(
            first_name='Uploaded OT',
            last_name='Test',
            biometric_id='BIO-UPLOADED-OT',
            salary=30000,
            position=StaffMember.Position.RECEPTIONIST,
            is_active=True,
        )
        imported, matched, errors = AttendanceImportService().import_summary_records([{
            'Biometric ID': staff.biometric_id,
            'Date': '2026-08-13',
            'Morning In': '08:00',
            'Morning Out': '12:00',
            'Afternoon In': '13:00',
            'Afternoon Out': '17:00',
            'Overtime In': '18:00',
            'Overtime Out': '20:00',
        }])
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

        self.assertEqual((imported, matched, errors), (1, 1, 0))
        self.assertEqual(payslip.overtime_hours, Decimal('2'))
        self.assertEqual(payslip.overtime_pay, Decimal('350.00'))

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

    def test_october_20_attendance_counts_only_in_second_half_when_monthly_summary_exists(self):
        set_setting('payroll_default_rest_days', 4)
        staff = StaffMember.objects.create(
            first_name='October',
            last_name='Attendance',
            biometric_id='BIO-OCT-20',
            salary=30000,
            position=StaffMember.Position.RECEPTIONIST,
            is_active=True,
        )
        MonthlyAttendanceSummary.objects.create(
            staff=staff,
            period_start=date(2026, 10, 1),
            period_end=date(2026, 10, 31),
            working_days=27,
            attendance_days=1,
            absence_days=26,
        )
        DailyAttendance.objects.create(
            staff=staff,
            attendance_date=date(2026, 10, 20),
            morning_in=datetime.strptime('08:00', '%H:%M').time(),
            morning_out=datetime.strptime('12:00', '%H:%M').time(),
            afternoon_in=datetime.strptime('13:00', '%H:%M').time(),
            afternoon_out=datetime.strptime('17:00', '%H:%M').time(),
            check_in=datetime.strptime('08:00', '%H:%M').time(),
            check_out=datetime.strptime('17:00', '%H:%M').time(),
            status='PRESENT',
            is_present=True,
            four_punch_complete=True,
        )
        first_half = PayrollPeriod.objects.create(
            month=10,
            year=2026,
            period_type=PayrollPeriod.PeriodType.SEMI_FIRST,
        )
        second_half = PayrollPeriod.objects.create(
            month=10,
            year=2026,
            period_type=PayrollPeriod.PeriodType.SEMI_SECOND,
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

        self.assertEqual(first_payslip.days_worked, 0)
        self.assertEqual(second_payslip.days_worked, 1)

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
        set_setting('payroll_default_overtime_pay_per_hour', Decimal('150.00'))
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
        self.assertEqual(payslip.overtime_pay, Decimal('825.00'))

    def test_statutory_master_toggle_controls_employee_deductions(self):
        settings = {
            'payroll_auto_statutory': False,
            'payroll_enable_sss': True,
            'payroll_sss_rate': Decimal('4.50'),
            'payroll_enable_philhealth': True,
            'payroll_philhealth_rate': Decimal('2.00'),
            'payroll_enable_pagibig': True,
            'payroll_pagibig_fixed': Decimal('100.00'),
        }
        payslip = Payslip(base_salary=Decimal('15000.00'))

        with patch(
            'settings.utils.get_setting',
            side_effect=lambda key, default=None: settings.get(key, default),
        ):
            payslip.calculate()

        self.assertEqual(payslip.sss, Decimal('0.00'))
        self.assertEqual(payslip.philhealth, Decimal('0.00'))
        self.assertEqual(payslip.pagibig, Decimal('0.00'))

        settings['payroll_auto_statutory'] = True
        with patch(
            'settings.utils.get_setting',
            side_effect=lambda key, default=None: settings.get(key, default),
        ):
            payslip.calculate()

        self.assertEqual(payslip.sss, Decimal('337.50'))
        self.assertEqual(payslip.philhealth, Decimal('150.00'))
        self.assertEqual(payslip.pagibig, Decimal('50.00'))

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
        self.assertEqual(payslip.rest_days_actual, 0)

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

    def test_payslip_uses_daily_salary_for_absent_deduction(self):
        set_setting('payroll_default_rest_days', 4)

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
        self.assertEqual(payslip.daily_salary, Decimal('15000') / Decimal('13'))
        self.assertEqual(payslip.absent_deduction, Decimal('15000.00'))

    def test_report_allowances_include_all_earnings(self):
        set_setting('payroll_auto_statutory', False)
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
