from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.test import Client, RequestFactory, TestCase, override_settings
from django.core.management import call_command
from django.urls import resolve, reverse
from django.utils import timezone

from accounts.activity_context import reset_current_actor, set_current_actor
from accounts.models import ActivityLog, User
from accounts.rbac_models import Module, ModulePermission, Role, SpecialPermission
from appointments.models import Appointment
from branches.models import Branch
from employees.models import StaffMember
from inquiries.models import Inquiry
from inventory.forms import ProductForm
from inventory.models import Product
from inventory.expiry_alerts import run_inventory_expiry_alert_job
from patients.models import Pet
from payroll.email_service import send_payslip_email
from payroll.models import Payslip, PayslipEmailLog, PayrollPeriod
from notifications.models import FollowUp, Notification
from records.models import MedicalRecord, RecordEntry
from notifications.context_processors import unread_notifications
from notifications.delivery import send_notification_email
from notifications.middleware import NotificationModuleReadMiddleware
from notifications.utils import (
    mark_module_notifications_read,
    notify_medical_record_follow_up,
    notify_follow_up_scheduled,
    notify_inquiry_received,
    notify_stock_transfer_approved,
    sync_appointment_follow_up_to_medical_record,
)
from notifications.views import get_allowed_notification_types_for_user
from notifications.signals import create_low_inventory_notification


class EmailDeliveryTests(TestCase):
    @patch('notifications.delivery.send_mail', return_value=0)
    def test_email_delivery_reports_backend_rejection(self, send_mail_mock):
        sent = send_notification_email(
            'Test', 'Body', ['person@example.com'], fail_silently=False
        )

        self.assertFalse(sent)
        send_mail_mock.assert_called_once()


class InventoryThresholdSettingsTests(TestCase):
    @patch('notifications.signals.notify_module_users')
    @patch('notifications.signals.get_setting')
    def test_zero_critical_threshold_is_not_replaced_by_default(
        self, get_setting_mock, notify_mock
    ):
        get_setting_mock.side_effect = lambda key, default=None: {
            'inventory_enable_alerts': True,
            'inventory_low_stock_threshold': 10,
            'inventory_critical_threshold': 0,
        }.get(key, default)

        create_low_inventory_notification(
            sender=Product,
            instance=SimpleNamespace(
                stock_quantity=3,
                name='Zero Threshold Test',
                branch=SimpleNamespace(pk=1),
                pk=1,
                id=1,
            ),
        )

        self.assertEqual(
            notify_mock.call_args.kwargs['title'],
            'Low Inventory Alert',
        )

    def test_payslip_delivery_is_idempotent(self):
        staff_user = User.objects.create_user(
            username='verified-payslip-staff',
            email='employee@example.com',
            password='A-secure-test-password-923!',
            email_verified=True,
        )
        staff = StaffMember.objects.create(
            user=staff_user,
            first_name='Test',
            last_name='Employee',
            email='different-profile-email@example.com',
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
        self.assertEqual(send_mock.call_args.kwargs['recipient_list'], [staff_user.email])
        self.assertEqual(
            PayslipEmailLog.objects.filter(payslip=payslip, status='SENT').count(), 1
        )

    def test_payslip_email_requires_verified_staff_account_email(self):
        staff_user = User.objects.create_user(
            username='unverified-payslip-staff',
            email='unverified@example.com',
            password='A-secure-test-password-923!',
            email_verified=False,
        )
        staff = StaffMember.objects.create(
            user=staff_user,
            first_name='Unverified',
            last_name='Employee',
            email='unverified@example.com',
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

        with patch('payroll.email_service.send_notification_email') as send_mock:
            sent, reason = send_payslip_email(payslip)

        self.assertFalse(sent)
        self.assertIn('verify their account email', reason)
        send_mock.assert_not_called()

    def test_inquiry_endpoint_requires_csrf(self):
        client = Client(enforce_csrf_checks=True)
        response = client.post('/inquiries/submit/', {
            'fullName': 'Test User',
            'email': 'test@example.com',
            'phone': '09123456789',
            'message': 'Hello',
        })

        self.assertEqual(response.status_code, 403)


class InventoryAlertEmailTests(TestCase):
    def test_low_stock_alert_sends_email_only_to_full_inventory_managers(self):
        branch = Branch.objects.create(name='Inventory Branch')
        inventory_module, _ = Module.objects.get_or_create(
            code='inventory',
            defaults={'name': 'Inventory'},
        )
        manager_role = Role.objects.create(
            name='Inventory Manager',
            code='inventory_manager',
            hierarchy_level=4,
        )
        ModulePermission.objects.create(
            role=manager_role,
            module=inventory_module,
            permission_type=ModulePermission.PermissionType.MANAGE,
            restrict_to_branch=True,
        )
        viewer_role = Role.objects.create(
            name='Inventory Viewer',
            code='inventory_viewer',
            hierarchy_level=3,
        )
        ModulePermission.objects.create(
            role=viewer_role,
            module=inventory_module,
            permission_type=ModulePermission.PermissionType.VIEW,
            restrict_to_branch=True,
        )

        superadmin = User.objects.create_superuser(
            username='stock-superadmin',
            email='superadmin@example.com',
            password='A-secure-test-password-923!',
        )
        inventory_manager = User.objects.create_user(
            username='inventory-manager',
            email='inventory.manager@example.com',
            password='A-secure-test-password-923!',
            assigned_role=manager_role,
            branch=branch,
        )
        inventory_viewer = User.objects.create_user(
            username='inventory-viewer',
            email='inventory.viewer@example.com',
            password='A-secure-test-password-923!',
            assigned_role=viewer_role,
            branch=branch,
        )

        with patch('notifications.signals.send_notification_email') as email_mock:
            Product.objects.create(
                name='Stock Alert Item',
                branch=branch,
                stock_quantity=3,
                price=30,
                unit_cost=20,
            )

        self.assertTrue(email_mock.called)
        emails = {
            email
            for call in email_mock.call_args_list
            for email in call.kwargs['recipient_list']
        }
        self.assertIn(superadmin.email, emails)
        self.assertIn(inventory_manager.email, emails)
        self.assertNotIn(inventory_viewer.email, emails)

    def test_new_item_with_initial_stock_does_not_trigger_low_stock_email(self):
        branch = Branch.objects.create(name='Inventory Branch')
        admin = User.objects.create_superuser(
            username='new-item-admin',
            email='new-item-admin@example.com',
            password='A-secure-test-password-923!',
        )
        form = ProductForm()
        form_data = {
            'branch': str(branch.pk),
            'item_type': form.fields['item_type'].choices[0][0],
            'name': 'Fresh Stock Item',
            'description': '',
            'sku': '',
            'manufacturer': '',
            'unit_of_measurement': form.fields['unit_of_measurement'].choices[0][0],
            'sale_type': form.fields['sale_type'].choices[0][0],
            'unit_cost': '15.00',
            'price': '30.00',
            'stock_quantity': '50',
            'expiration_date': '',
            'is_available': 'on',
        }

        with patch('notifications.signals.send_notification_email') as email_mock:
            self.client.force_login(admin)
            response = self.client.post(reverse('inventory:product_new'), form_data)

        self.assertEqual(response.status_code, 302)
        self.assertFalse(email_mock.called)
        self.assertEqual(Product.objects.get(name='Fresh Stock Item').stock_quantity, 50)


class InventoryExpiryEmailTests(TestCase):
    def test_30_day_expiry_email_targets_managers_and_superadmins_once(self):
        branch = Branch.objects.create(name='Expiry Email Branch')
        other_branch = Branch.objects.create(name='Other Expiry Branch')
        inventory_module, _ = Module.objects.get_or_create(
            code='inventory',
            defaults={'name': 'Inventory'},
        )
        manager_role = Role.objects.create(
            name='Expiry Inventory Manager',
            code='expiry-inventory-manager',
            hierarchy_level=2,
        )
        ModulePermission.objects.create(
            role=manager_role,
            module=inventory_module,
            permission_type=ModulePermission.PermissionType.MANAGE,
            restrict_to_branch=True,
        )
        viewer_role = Role.objects.create(
            name='Expiry Inventory Viewer',
            code='expiry-inventory-viewer',
            hierarchy_level=1,
        )
        ModulePermission.objects.create(
            role=viewer_role,
            module=inventory_module,
            permission_type=ModulePermission.PermissionType.VIEW,
            restrict_to_branch=True,
        )
        superadmin = User.objects.create_superuser(
            username='expiry-superadmin',
            email='expiry.superadmin@example.com',
            password='A-secure-test-password-923!',
        )
        manager = User.objects.create_user(
            username='expiry-manager',
            email='expiry.manager@example.com',
            password='A-secure-test-password-923!',
            assigned_role=manager_role,
            branch=branch,
        )
        other_branch_manager = User.objects.create_user(
            username='expiry-other-manager',
            email='expiry.other@example.com',
            password='A-secure-test-password-923!',
            assigned_role=manager_role,
            branch=other_branch,
        )
        viewer = User.objects.create_user(
            username='expiry-viewer',
            email='expiry.viewer@example.com',
            password='A-secure-test-password-923!',
            assigned_role=viewer_role,
            branch=branch,
        )
        expiry_date = timezone.localdate() + timedelta(days=30)
        with patch('notifications.signals.run_inventory_expiry_alert_job'):
            product = Product.objects.create(
                name='Expiring Test Medication',
                branch=branch,
                stock_quantity=40,
                price=30,
                unit_cost=20,
                expiration_date=expiry_date,
            )

        setting_values = {
            'inventory_enable_alerts': True,
            'inventory_expiry_warning_days': 30,
        }
        with patch(
            'inventory.expiry_alerts.get_setting',
            side_effect=lambda key, default=None: setting_values.get(key, default),
        ), patch(
            'inventory.expiry_alerts.send_notification_email',
            return_value=True,
        ) as email_mock:
            with self.captureOnCommitCallbacks(execute=True):
                first_summary = run_inventory_expiry_alert_job()
            with self.captureOnCommitCallbacks(execute=True):
                repeat_summary = run_inventory_expiry_alert_job()

        self.assertEqual(first_summary['emails_sent'], 2)
        self.assertEqual(repeat_summary['emails_sent'], 0)
        self.assertEqual(email_mock.call_count, 1)
        email = email_mock.call_args.kwargs
        self.assertEqual(
            set(email['recipient_list']),
            {superadmin.email, manager.email},
        )
        self.assertNotIn(other_branch_manager.email, email['recipient_list'])
        self.assertNotIn(viewer.email, email['recipient_list'])
        self.assertIn('Expiring Test Medication', email['message'])
        self.assertIn(branch.name, email['message'])
        self.assertIn(expiry_date.isoformat(), email['message'])
        self.assertIn('expires in 30 days', email['subject'])

        Product.objects.filter(pk=product.pk).update(
            expiration_date=timezone.localdate() + timedelta(days=29)
        )
        run_inventory_expiry_alert_job(product_ids=[product.pk])
        self.assertEqual(email_mock.call_count, 1)


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
            defaults={'name': 'Cashier', 'hierarchy_level': 2},
        )
        self.receptionist_role, _ = Role.objects.get_or_create(
            code='receptionist',
            defaults={'name': 'Legacy Receptionist', 'hierarchy_level': 2},
        )
        self.executive_role, _ = Role.objects.get_or_create(
            code='executive_officer',
            defaults={'name': 'Branch Administrator', 'hierarchy_level': 4},
        )

    def test_mark_read_endpoint_marks_only_the_current_users_notification(self):
        notification = Notification.objects.create(
            user=self.pet_owner,
            title='Reservation update',
            message='Your reservation is ready.',
            module_context=Notification.ModuleContext.INVENTORY,
        )
        self.client.force_login(self.pet_owner)

        response = self.client.post(
            reverse('notifications:mark_read', args=[notification.pk]),
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['success'])
        notification.refresh_from_db()
        self.assertTrue(notification.is_read)

    def test_delete_notification_removes_it_from_database(self):
        notification = Notification.objects.create(
            user=self.pet_owner,
            title='Reservation update',
            message='Your reservation is ready.',
            module_context=Notification.ModuleContext.INVENTORY,
        )
        self.client.force_login(self.pet_owner)

        response = self.client.post(
            reverse('notifications:delete_notification', args=[notification.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['success'])
        self.assertFalse(Notification.objects.filter(pk=notification.pk).exists())

    def create_linked_record_and_appointment(self, ff_up):
        today = timezone.localdate()
        pet = Pet.objects.create(
            owner=self.pet_owner,
            source=Pet.Source.PORTAL,
            name='Milo',
            species='Dog',
            sex=Pet.Sex.MALE,
        )
        appointment = Appointment.objects.create(
            owner_name='Pet Owner',
            owner_email='owner@example.com',
            pet_name=pet.name,
            pet=pet,
            user=self.pet_owner,
            branch=self.branch,
            appointment_date=today,
            appointment_time=timezone.localtime().time().replace(microsecond=0),
        )
        record = MedicalRecord.objects.create(
            pet=pet,
            date_recorded=today,
            ff_up=ff_up,
        )
        entry = RecordEntry.objects.create(
            record=record,
            appointment=appointment,
            date_recorded=today,
            ff_up=ff_up,
            follow_up_reason='Medical record follow-up',
        )
        return appointment, record, entry

    def test_open_inventory_notification_marks_read_and_opens_catalog_for_pet_owner(self):
        notification = Notification.objects.create(
            user=self.pet_owner,
            title='Reservation update',
            message='Your reservation is ready.',
            module_context=Notification.ModuleContext.INVENTORY,
        )
        self.client.force_login(self.pet_owner)

        response = self.client.get(
            reverse('notifications:open_notification', args=[notification.pk])
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], reverse('inventory:catalog'))
        notification.refresh_from_db()
        self.assertTrue(notification.is_read)

    @patch(
        'notifications.followup_email_service.send_notification_email',
        return_value=True,
    )
    def test_follow_up_email_identifies_recommendation_not_booking(self, send_email):
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
            follow_up_date=timezone.localdate() + timedelta(days=7),
            reason='Medication recheck',
        )
        from notifications.followup_email_service import send_follow_up_email

        result = send_follow_up_email(follow_up)

        self.assertEqual(result, (True, 'Sent.'))
        email_message = send_email.call_args.kwargs['message']
        self.assertIn('recommended', email_message)
        self.assertIn('not a confirmed appointment', email_message)
        self.assertIn('Medication recheck', email_message)

    @override_settings(STORAGES={
        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
        'staticfiles': {
            'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage',
        },
    })
    def test_notification_cards_link_to_open_route_in_both_portals(self):
        notification = Notification.objects.create(
            user=self.pet_owner,
            title='Appointment update',
            message='Your appointment was updated.',
            module_context=Notification.ModuleContext.APPOINTMENTS,
        )
        self.client.force_login(self.pet_owner)

        response = self.client.get(reverse('notifications:notification_list'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            reverse('notifications:open_notification', args=[notification.pk]),
        )
        self.assertContains(response, 'id="deleteNotificationModal"')
        self.assertContains(response, 'onclick="openDeleteNotification(event, this)"')

        superadmin = User.objects.create_superuser(
            username='notification-link-admin',
            password='A-secure-test-password-923!',
            email='notification-link-admin@example.com',
        )
        admin_notification = Notification.objects.create(
            user=superadmin,
            title='Clinic update',
            message='Clinic notification.',
            module_context=Notification.ModuleContext.GENERAL,
        )
        self.client.force_login(superadmin)

        response = self.client.get(reverse('notifications:admin_notifications'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            reverse('notifications:open_notification', args=[admin_notification.pk]),
        )
        self.assertContains(response, 'id="deleteNotificationModal"')
        self.assertContains(response, 'onclick="openDeleteNotification(event, this)"')

    def test_marking_module_notifications_read_does_not_clear_other_modules(self):
        inventory_notification = Notification.objects.create(
            user=self.pet_owner,
            title='Reservation update',
            message='Your reservation is ready.',
            module_context=Notification.ModuleContext.INVENTORY,
        )
        inquiry_notification = Notification.objects.create(
            user=self.pet_owner,
            title='Inquiry update',
            message='Your inquiry was answered.',
            module_context=Notification.ModuleContext.INQUIRIES,
        )

        mark_module_notifications_read(
            self.pet_owner,
            Notification.ModuleContext.INVENTORY,
        )

        inventory_notification.refresh_from_db()
        inquiry_notification.refresh_from_db()
        self.assertTrue(inventory_notification.is_read)
        self.assertFalse(inquiry_notification.is_read)

    def test_module_navigation_marks_only_its_notifications_read(self):
        inventory_notification = Notification.objects.create(
            user=self.pet_owner,
            title='Reservation update',
            message='Your reservation is ready.',
            module_context=Notification.ModuleContext.INVENTORY,
        )
        inquiry_notification = Notification.objects.create(
            user=self.pet_owner,
            title='Inquiry update',
            message='Your inquiry was answered.',
            module_context=Notification.ModuleContext.INQUIRIES,
        )
        request = RequestFactory().get('/inventory/catalog/')
        request.user = self.pet_owner
        request.resolver_match = resolve('/inventory/catalog/')

        NotificationModuleReadMiddleware(lambda _request: None).process_view(
            request, None, (), {},
        )

        inventory_notification.refresh_from_db()
        inquiry_notification.refresh_from_db()
        self.assertTrue(inventory_notification.is_read)
        self.assertFalse(inquiry_notification.is_read)

    def test_module_read_middleware_ignores_inventory_api_requests(self):
        notification = Notification.objects.create(
            user=self.pet_owner,
            title='Reservation update',
            message='Your reservation is ready.',
            module_context=Notification.ModuleContext.INVENTORY,
        )
        request = RequestFactory().get('/inventory/get-branch-products/1/')
        request.user = self.pet_owner
        request.resolver_match = resolve('/inventory/get-branch-products/1/')

        NotificationModuleReadMiddleware(lambda _request: None).process_view(
            request, None, (), {},
        )

        notification.refresh_from_db()
        self.assertFalse(notification.is_read)

    def test_module_read_middleware_handles_unnamed_routes(self):
        request = RequestFactory().get('/media/profiles/Carl.jpg')
        request.user = self.pet_owner
        request.resolver_match = SimpleNamespace(app_name='', url_name=None)

        result = NotificationModuleReadMiddleware(lambda _request: None).process_view(
            request, None, (), {},
        )

        self.assertIsNone(result)

    def test_pet_portal_combines_and_clears_pet_and_medical_record_alerts(self):
        patient_notification = Notification.objects.create(
            user=self.pet_owner,
            title='Pet update',
            message='Your pet profile was updated.',
            module_context=Notification.ModuleContext.PATIENTS,
        )
        record_notification = Notification.objects.create(
            user=self.pet_owner,
            title='Medical record update',
            message='A medical record was added.',
            module_context=Notification.ModuleContext.MEDICAL_RECORDS,
        )
        request = RequestFactory().get('/patients/my-pets/')
        request.user = self.pet_owner
        request.resolver_match = resolve('/patients/my-pets/')

        context = unread_notifications(request)
        NotificationModuleReadMiddleware(lambda _request: None).process_view(
            request, None, (), {},
        )

        self.assertEqual(context['unread_pet_notifications_count'], 2)
        patient_notification.refresh_from_db()
        record_notification.refresh_from_db()
        self.assertTrue(patient_notification.is_read)
        self.assertTrue(record_notification.is_read)

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
        send_email.assert_called_once_with(follow_up, event='scheduled')

    @patch('notifications.followup_email_service.send_follow_up_email')
    def test_updated_follow_up_notifies_owner_and_sends_updated_email(self, send_email):
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
            follow_up_date=timezone.localdate() + timezone.timedelta(days=7),
        )
        send_email.return_value = (True, 'Sent.')

        with self.captureOnCommitCallbacks(execute=True):
            notify_follow_up_scheduled(
                appointment,
                follow_up,
                follow_up_reason='Medication review',
                event='updated',
            )

        notification = Notification.objects.get(related_follow_up=follow_up)
        self.assertEqual(notification.user, self.pet_owner)
        self.assertIn('updated', notification.message)
        self.assertIn('Medication review', notification.message)
        send_email.assert_called_once_with(follow_up, event='updated')

    @patch('notifications.followup_email_service.send_follow_up_email')
    def test_medical_record_follow_up_updates_its_linked_appointment(self, send_email):
        original_date = timezone.localdate() + timezone.timedelta(days=7)
        updated_date = timezone.localdate() + timezone.timedelta(days=14)
        appointment, record, entry = self.create_linked_record_and_appointment(
            updated_date,
        )
        follow_up = FollowUp.objects.create(
            appointment=appointment,
            pet_name=record.pet.name,
            follow_up_date=original_date,
        )
        send_email.return_value = (True, 'Sent.')

        with self.captureOnCommitCallbacks(execute=True):
            synchronized = notify_medical_record_follow_up(record, self.pet_owner)

        follow_up.refresh_from_db()
        entry.refresh_from_db()
        self.assertEqual(synchronized.pk, follow_up.pk)
        self.assertEqual(follow_up.follow_up_date, updated_date)
        self.assertEqual(follow_up.medical_record_id, record.pk)
        self.assertEqual(entry.ff_up, updated_date)
        send_email.assert_called_once_with(follow_up, event='updated')

    @patch('notifications.utils.create_notification')
    @patch('notifications.followup_email_service.send_follow_up_email')
    def test_medical_record_follow_up_saves_reason_and_emails_owner(
        self, send_email, create_notification_mock,
    ):
        follow_up_date = timezone.localdate() + timedelta(days=8)
        appointment, record, entry = self.create_linked_record_and_appointment(
            follow_up_date,
        )
        entry.follow_up_reason = 'Recheck response to medication'
        entry.save(update_fields=['follow_up_reason'])
        send_email.return_value = (True, 'Sent.')

        with self.captureOnCommitCallbacks(execute=True):
            followup = notify_medical_record_follow_up(record, self.pet_owner)

        self.assertEqual(followup.appointment_id, appointment.pk)
        self.assertEqual(
            followup.reason,
            'Recheck response to medication',
        )
        notification_message = create_notification_mock.call_args.kwargs['message']
        self.assertIn('Recheck response to medication', notification_message)
        self.assertIn('not a confirmed appointment', notification_message)
        send_email.assert_called_once_with(followup, event='scheduled')

    def test_appointment_follow_up_updates_its_linked_medical_record(self):
        original_date = timezone.localdate() + timezone.timedelta(days=7)
        updated_date = timezone.localdate() + timezone.timedelta(days=14)
        appointment, record, entry = self.create_linked_record_and_appointment(
            original_date,
        )
        follow_up = FollowUp.objects.create(
            appointment=appointment,
            pet_name=record.pet.name,
            follow_up_date=updated_date,
        )

        synchronized_record = sync_appointment_follow_up_to_medical_record(
            appointment, follow_up,
        )

        record.refresh_from_db()
        entry.refresh_from_db()
        follow_up.refresh_from_db()
        self.assertEqual(synchronized_record.pk, record.pk)
        self.assertEqual(record.ff_up, updated_date)
        self.assertEqual(entry.ff_up, updated_date)
        self.assertEqual(follow_up.medical_record_id, record.pk)

    @patch(
        'notifications.management.commands.send_followup_emails.'
        'send_follow_up_reminder_email',
        return_value=(True, 'Sent.'),
    )
    def test_three_day_follow_up_reminder_creates_owner_notification(self, send_email):
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
            follow_up_date=timezone.localdate() + timezone.timedelta(days=3),
        )

        with self.captureOnCommitCallbacks(execute=True):
            call_command('send_followup_emails')

        send_email.assert_called_once_with(follow_up)
        notification = Notification.objects.get(related_follow_up=follow_up)
        self.assertEqual(notification.user, self.pet_owner)
        self.assertIn('in 3 days', notification.message)

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
            defaults={'name': 'Veterinarian', 'hierarchy_level': 3},
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

    def test_stock_transfer_approval_notifies_requester_and_is_visible(self):
        transfer_role, _ = Role.objects.get_or_create(
            code='transfer-requester',
            defaults={'name': 'Transfer Requester', 'hierarchy_level': 2},
        )
        special_permission, _ = SpecialPermission.objects.get_or_create(
            code='can_request_stock_transfer',
            defaults={
                'name': 'Request Stock Transfer',
                'description': 'Can request stock from another branch.',
            },
        )
        transfer_role.special_permissions.get_or_create(permission=special_permission)
        requester = User.objects.create_user(
            username='transfer-requester',
            assigned_role=transfer_role,
            branch=self.branch,
        )
        transfer = SimpleNamespace(
            pk=23,
            id=23,
            quantity=4,
            source_product=SimpleNamespace(
                name='Pet Medication', branch=self.branch,
            ),
            requested_by=requester,
        )

        with self.captureOnCommitCallbacks(execute=True):
            notify_stock_transfer_approved(transfer)

        notification = Notification.scoped_for_user(requester).get(
            related_object_id=transfer.pk,
            notification_type=Notification.NotificationType.STOCK_TRANSFER_APPROVED,
        )
        allowed_types = {
            code for code, _ in get_allowed_notification_types_for_user(requester)
        }
        self.assertIn(Notification.NotificationType.STOCK_TRANSFER_APPROVED, allowed_types)
        self.assertIn('was approved', notification.message)
        self.assertFalse(notification.is_read)
