from decimal import Decimal
from unittest.mock import patch

from django.test import Client, TestCase

from employees.models import StaffMember
from payroll.email_service import send_payslip_email
from payroll.models import Payslip, PayslipEmailLog, PayrollPeriod
from notifications.delivery import send_notification_email


class EmailDeliveryTests(TestCase):
    @patch('notifications.delivery.send_mail', return_value=0)
    def test_email_delivery_reports_backend_rejection(self, send_mail_mock):
        sent = send_notification_email(
            'Test', 'Body', ['person@example.com'], fail_silently=False
        )

        self.assertFalse(sent)
        send_mail_mock.assert_called_once()

    def test_payslip_delivery_is_idempotent(self):
        staff = StaffMember.objects.create(
            first_name='Test',
            last_name='Employee',
            email='employee@example.com',
            salary=Decimal('30000'),
            position=StaffMember.Position.RECEPTIONIST,
        )
        period = PayrollPeriod.objects.create(
            month=9,
            year=2026,
            period_type=PayrollPeriod.PeriodType.SEMI_FIRST,
        )
        payslip = Payslip.objects.create(
            payroll_period=period,
            employee=staff,
            base_salary=Decimal('15000'),
            gross_pay=Decimal('15000'),
            net_pay=Decimal('14500'),
        )

        with patch('payroll.email_service.send_notification_email', return_value=True) as send_mock:
            self.assertEqual((True, 'Sent.'), send_payslip_email(payslip))
            self.assertEqual((True, 'Already sent.'), send_payslip_email(payslip))

        self.assertEqual(send_mock.call_count, 1)
        self.assertEqual(
            PayslipEmailLog.objects.filter(payslip=payslip, status='SENT').count(), 1
        )

    def test_inquiry_endpoint_requires_csrf(self):
        client = Client(enforce_csrf_checks=True)
        response = client.post('/inquiries/submit/', {
            'fullName': 'Test User',
            'email': 'test@example.com',
            'phone': '09123456789',
            'message': 'Hello',
        })

        self.assertEqual(response.status_code, 403)
