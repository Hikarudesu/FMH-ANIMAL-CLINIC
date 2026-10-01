from decimal import Decimal
from unittest.mock import patch

from django.test import Client, TestCase
from django.utils import timezone

from accounts.activity_context import reset_current_actor, set_current_actor
from accounts.models import ActivityLog, User
from accounts.rbac_models import Role
from appointments.models import Appointment
from branches.models import Branch
from employees.models import StaffMember
from inquiries.models import Inquiry
from payroll.email_service import send_payslip_email
from payroll.models import Payslip, PayslipEmailLog, PayrollPeriod
from notifications.models import FollowUp, Notification
from notifications.delivery import send_notification_email
from notifications.utils import notify_follow_up_scheduled, notify_inquiry_received
from notifications.views import get_allowed_notification_types_for_user


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


class NotificationRoutingTests(TestCase):
    def setUp(self):
        self.branch = Branch.objects.create(name='Test Branch')
        self.pet_owner = User.objects.create_user(
            username='pet-owner',
            email='owner@example.com',
            first_name='Pet',
            last_name='Owner',
        )
        self.cashier_role, _ = Role.objects.get_or_create(
            code='cashier',
            defaults={'name': 'Cashier', 'hierarchy_level': 4},
        )
        self.receptionist_role, _ = Role.objects.get_or_create(
            code='receptionist',
            defaults={'name': 'Legacy Receptionist', 'hierarchy_level': 4},
        )
        self.executive_role, _ = Role.objects.get_or_create(
            code='executive_officer',
            defaults={'name': 'Branch Administrator', 'hierarchy_level': 8},
        )

    @patch('notifications.followup_email_service.send_follow_up_email')
    def test_scheduled_follow_up_notifies_portal_and_registered_email(self, send_email):
        appointment = Appointment.objects.create(
            owner_name='Pet Owner',
            owner_email='owner@example.com',
            pet_name='Milo',
            branch=self.branch,
            appointment_date=timezone.localdate(),
            appointment_time=timezone.localtime().time().replace(microsecond=0),
            user=self.pet_owner,
        )
        follow_up = FollowUp.objects.create(
            appointment=appointment,
            pet_name='Milo',
            follow_up_date=timezone.localdate(),
        )
        send_email.return_value = (True, 'Sent.')

        with self.captureOnCommitCallbacks(execute=True):
            notify_follow_up_scheduled(appointment, follow_up)

        self.assertTrue(Notification.objects.filter(
            user=self.pet_owner,
            notification_type=Notification.NotificationType.FOLLOW_UP,
            related_follow_up=follow_up,
        ).exists())
        send_email.assert_called_once_with(follow_up)

    @patch('notifications.signals.notify_inquiry_received')
    def test_inquiry_reaches_branch_admin_and_receptionist_alias(self, signal_notifier):
        cashier = User.objects.create_user(
            username='cashier', assigned_role=self.cashier_role, branch=self.branch,
        )
        legacy_receptionist = User.objects.create_user(
            username='receptionist', assigned_role=self.receptionist_role, branch=self.branch,
        )
        branch_admin = User.objects.create_user(
            username='branch-admin', assigned_role=self.executive_role, branch=self.branch,
        )

        inquiry = Inquiry.objects.create(
            full_name='New Client',
            email='client@example.com',
            phone='09123456789',
            message='Please call me.',
            branch=self.branch,
        )
        with self.captureOnCommitCallbacks(execute=True):
            notify_inquiry_received(inquiry)
        signal_notifier.assert_called_once_with(inquiry)

        recipients = set(Notification.objects.values_list('user__username', flat=True))
        self.assertEqual(recipients, {'cashier', 'receptionist', 'branch-admin'})

    def test_inquiry_delete_is_attributed_to_current_actor(self):
        actor = User.objects.create_user(username='actor')
        inquiry = Inquiry.objects.create(
            full_name='Delete Me',
            email='client@example.com',
            phone='09123456789',
            message='Temporary inquiry.',
            branch=self.branch,
        )
        token = set_current_actor(actor)
        try:
            inquiry.delete()
        finally:
            reset_current_actor(token)

        self.assertTrue(ActivityLog.objects.filter(
            user=actor,
            object_type='Inquiry',
            action_type=ActivityLog.ActionType.DELETE,
        ).exists())

    def test_notification_types_are_scoped_for_owner_staff_and_superadmin(self):
        superadmin = User.objects.create_superuser(
            username='superadmin', password='password', email='admin@example.com',
        )
        vet_role, _ = Role.objects.get_or_create(
            code='veterinarian',
            defaults={'name': 'Veterinarian', 'hierarchy_level': 5},
        )
        vet = User.objects.create_user(
            username='vet', assigned_role=vet_role, branch=self.branch,
        )

        owner_types = {code for code, _ in get_allowed_notification_types_for_user(self.pet_owner)}
        vet_types = {code for code, _ in get_allowed_notification_types_for_user(vet)}
        superadmin_types = {
            code for code, _ in get_allowed_notification_types_for_user(superadmin)
        }

        self.assertIn(Notification.NotificationType.FOLLOW_UP, owner_types)
        self.assertNotIn(Notification.NotificationType.INQUIRY_NEW, owner_types)
        self.assertNotIn(Notification.NotificationType.PAYROLL_RELEASED, vet_types)
        self.assertIn(Notification.NotificationType.INQUIRY_NEW, superadmin_types)
        self.assertIn(Notification.NotificationType.PAYROLL_RELEASED, superadmin_types)
