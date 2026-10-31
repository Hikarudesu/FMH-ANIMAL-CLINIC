from datetime import time
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from accounts.rbac_models import Role, SpecialPermission
from appointments.models import Appointment
from billing.models import Service
from branches.models import Branch
from inventory.models import Product, Reservation
from pos.models import Payment, Refund, Sale, SaleItem
from settings.utils import set_setting


@override_settings(STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {
        'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage',
    },
})
class AppointmentCheckoutTests(TestCase):
    def setUp(self):
        self.branch = Branch.objects.create(name='Appointment POS Branch')
        self.cashier = User.objects.create_user(
            username='appointment-pos-cashier',
            email='appointment-pos-cashier@example.com',
            password='A-secure-test-password-923!',
            branch=self.branch,
            is_superuser=True,
            is_staff=True,
        )
        self.appointment = Appointment.objects.create(
            owner_name='POS Appointment Owner',
            owner_email='owner@example.com',
            pet_name='POS Appointment Pet',
            branch=self.branch,
            appointment_date=timezone.localdate(),
            appointment_time=time(10),
            status=Appointment.Status.AWAITING_PAYMENT,
        )
        self.client.force_login(self.cashier)

    def test_appointment_checkout_creates_and_links_pending_sale(self):
        response = self.client.get(
            reverse('pos:checkout'),
            {'appointment': self.appointment.pk},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'POS Appointment Pet')
        self.assertContains(response, 'Return to appointment')
        self.appointment.refresh_from_db()
        self.assertIsNotNone(self.appointment.sale_id)
        self.assertEqual(self.appointment.sale.branch_id, self.branch.pk)
        self.assertEqual(self.appointment.sale.cashier_id, self.cashier.pk)
        self.assertEqual(self.appointment.sale.status, 'PENDING')

    def test_pos_tabs_and_inventory_results_follow_configured_item_types(self):
        set_setting('inventory_item_type_options', ['Medical Supplies'])
        supply = Product.objects.create(
            branch=self.branch,
            item_type='Medical Supplies',
            name='Sterile Gauze',
            price=25,
            stock_quantity=8,
        )
        Product.objects.create(
            branch=self.branch,
            item_type='Medication',
            name='Hidden Medication',
            price=10,
            stock_quantity=4,
        )

        checkout_response = self.client.get(reverse('pos:checkout'))
        self.assertContains(
            checkout_response,
            'data-category="medical-supplies">Medical Supplies',
        )
        self.assertNotContains(checkout_response, 'data-category="medication"')

        items_response = self.client.get(
            reverse('pos:filter_items'),
            {'branch_id': self.branch.pk},
        )

        self.assertEqual(items_response.status_code, 200)
        self.assertEqual(
            [item['id'] for item in items_response.json()['results']],
            [supply.pk],
        )
        self.assertEqual(items_response.json()['results'][0]['type'], 'PRODUCT')
        self.assertEqual(items_response.json()['results'][0]['category'], 'medical-supplies')
        self.assertEqual(items_response.json()['results'][0]['category_label'], 'Medical Supplies')

        sale = checkout_response.context['sale']
        add_response = self.client.post(
            reverse('pos:add_item'),
            {
                'sale_id': sale.pk,
                'item_type': items_response.json()['results'][0]['type'],
                'item_id': supply.pk,
                'quantity': 1,
            },
        )

        self.assertEqual(add_response.status_code, 200)
        self.assertTrue(add_response.json()['success'])
        sale_item = SaleItem.objects.get(sale=sale, product=supply)
        self.assertEqual(sale_item.item_type, SaleItem.ItemType.PRODUCT)

    def test_linked_appointment_payment_reaches_validation(self):
        sale = Sale.objects.create(
            branch=self.branch,
            cashier=self.cashier,
        )
        self.appointment.sale = sale
        self.appointment.save(update_fields=['sale', 'updated_at'])

        response = self.client.post(
            reverse('pos:process_payment'),
            {
                'sale_id': sale.pk,
                'amount': '1.00',
                'method': 'CASH',
                'customer_type': Sale.CustomerType.WALKIN,
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['error'], 'Cannot process empty sale')
        self.appointment.refresh_from_db()
        sale.refresh_from_db()
        self.assertEqual(self.appointment.status, Appointment.Status.AWAITING_PAYMENT)
        self.assertEqual(sale.status, Sale.Status.PENDING)

    @patch('pos.views.create_or_release_soa_for_sale')
    def test_registered_customer_payment_succeeds_without_selecting_pet(self, _release_soa):
        customer = User.objects.create_user(
            username='registered-pos-customer',
            email='registered-pos-customer@example.com',
            password='A-secure-test-password-923!',
            is_superuser=False,
        )
        service = Service.objects.create(name='Consultation', price=100)
        sale = Sale.objects.create(branch=self.branch, cashier=self.cashier)
        SaleItem.objects.create(
            sale=sale,
            item_type=SaleItem.ItemType.SERVICE,
            service=service,
            name=service.name,
            unit_price=service.price,
            quantity=1,
        )

        response = self.client.post(
            reverse('pos:process_payment'),
            {
                'sale_id': sale.pk,
                'amount': '100.00',
                'method': 'CASH',
                'customer_type': Sale.CustomerType.REGISTERED,
                'customer_id': customer.pk,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['completed'])
        sale.refresh_from_db()
        self.assertEqual(sale.status, Sale.Status.COMPLETED)
        self.assertEqual(sale.customer_id, customer.pk)
        self.assertIsNone(sale.pet_id)

    def test_payment_is_rolled_back_when_stock_is_insufficient(self):
        product = Product.objects.create(
            branch=self.branch,
            item_type='Product',
            name='Out of Stock Item',
            price=20,
            stock_quantity=0,
        )
        sale = Sale.objects.create(
            branch=self.branch,
            cashier=self.cashier,
            subtotal=20,
            total=20,
        )
        SaleItem.objects.create(
            sale=sale,
            item_type=SaleItem.ItemType.PRODUCT,
            product=product,
            name=product.name,
            unit_price=20,
            quantity=1,
        )

        response = self.client.post(
            reverse('pos:process_payment'),
            {
                'sale_id': sale.pk,
                'amount': '20.00',
                'method': 'CASH',
                'customer_type': Sale.CustomerType.WALKIN,
            },
        )

        self.assertEqual(response.status_code, 409)
        self.assertFalse(response.json()['success'])
        self.assertEqual(Payment.objects.filter(sale=sale).count(), 0)
        sale.refresh_from_db()
        self.assertEqual(sale.status, Sale.Status.PENDING)

    @patch('pos.views.create_or_release_soa_for_sale')
    def test_reservation_checkout_prefills_and_releases_after_payment(self, _release_soa):
        customer = User.objects.create_user(
            username='reservation-pos-customer',
            email='reservation-pos-customer@example.com',
            password='A-secure-test-password-923!',
        )
        product = Product.objects.create(
            branch=self.branch,
            item_type='Product',
            name='Reserved Food',
            price=35,
            stock_quantity=3,
        )
        reservation = Reservation.objects.create(
            user=customer,
            product=product,
            quantity=2,
            status=Reservation.Status.PENDING,
        )

        checkout_response = self.client.get(
            reverse('pos:checkout'),
            {'reservation': reservation.pk},
        )

        self.assertEqual(checkout_response.status_code, 200)
        sale = checkout_response.context['sale']
        self.assertEqual(sale.customer_id, customer.pk)
        self.assertEqual(sale.items.get().quantity, 2)
        self.assertContains(checkout_response, 'Reservation payment')

        payment_response = self.client.post(
            reverse('pos:process_payment'),
            {
                'sale_id': sale.pk,
                'amount': '70.00',
                'method': 'CASH',
                'customer_type': Sale.CustomerType.WALKIN,
            },
        )

        self.assertEqual(payment_response.status_code, 200)
        self.assertTrue(payment_response.json()['completed'])
        reservation.refresh_from_db()
        product.refresh_from_db()
        sale.refresh_from_db()
        self.assertEqual(reservation.status, Reservation.Status.RELEASED)
        self.assertEqual(reservation.sale_id, sale.pk)
        self.assertEqual(product.stock_quantity, 3)
        self.assertEqual(sale.status, Sale.Status.COMPLETED)

    def test_receipt_autoprints_only_after_checkout_and_has_no_manual_print_action(self):
        sale = Sale.objects.create(
            branch=self.branch,
            cashier=self.cashier,
        )

        response = self.client.get(
            reverse('pos:receipt', kwargs={'sale_id': sale.pk}),
            {'autoprint': '1'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "get('autoprint') === '1'")
        self.assertContains(response, 'sessionStorage.getItem(printGuardKey)')
        self.assertContains(response, 'window.print();')
        self.assertContains(response, "window.addEventListener('afterprint'")
        self.assertContains(response, "get('embedded') !== '1'")
        self.assertContains(response, "window.opener.postMessage({ type: 'pos-receipt-printed' }")
        self.assertNotContains(response, 'Print Receipt')
        self.assertNotContains(response, 'onclick="window.print()"')
        self.assertContains(response, 'width: 44mm;')
        self.assertContains(response, 'color: #000 !important;')
        self.assertContains(response, 'font-family: Arial, sans-serif;')
        self.assertContains(response, 'letter-spacing: 0.5px;')
        self.assertContains(response, 'width: 56mm;')
        self.assertContains(response, 'margin: 0 auto;')
        self.assertContains(response, 'padding: 0 2mm;')
        self.assertContains(response, 'grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);')

    def test_checkout_prints_receipt_in_current_page_without_popup(self):
        response = self.client.get(reverse('pos:checkout'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'async function printCompletedSaleReceipt(completedSaleId)')
        self.assertContains(response, "receiptDocument.querySelector('.receipt')")
        self.assertContains(response, 'window.print();')
        self.assertContains(response, 'body.pos-printing .receipt')
        self.assertNotContains(response, 'window.open(')
        self.assertNotContains(response, 'Print Receipt')


@override_settings(STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {
        'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage',
    },
})
class SaleVoidPermissionTests(TestCase):
    def setUp(self):
        self.branch = Branch.objects.create(name='Sale Void Permission Branch')
        self.role = Role.objects.create(
            name='POS Access Without Void',
            code='pos-access-without-void',
            hierarchy_level=2,
            is_staff_role=True,
        )
        pos_permission, _ = SpecialPermission.objects.get_or_create(
            code='can_access_pos',
            defaults={'name': 'Point of Sale Access'},
        )
        self.role.special_permissions.create(permission=pos_permission)
        self.user = User.objects.create_user(
            username='pos-access-without-void',
            password='A-secure-test-password-944!',
            assigned_role=self.role,
            branch=self.branch,
        )
        self.sale = Sale.objects.create(
            branch=self.branch,
            cashier=self.user,
            status=Sale.Status.COMPLETED,
            subtotal=100,
            total=100,
            amount_paid=100,
        )
        self.client.force_login(self.user)

    def test_pos_access_without_void_grant_hides_and_denies_void_action(self):
        detail_response = self.client.get(
            reverse('pos:sale_detail', args=[self.sale.pk]),
        )
        self.assertEqual(detail_response.status_code, 200)
        self.assertNotContains(detail_response, 'Void Sale')

        response = self.client.post(
            reverse('pos:void_sale', args=[self.sale.pk]),
            {'reason': 'Test'},
        )

        self.assertRedirects(response, reverse('pos:sales_list'))
        self.sale.refresh_from_db()
        self.assertEqual(self.sale.status, Sale.Status.COMPLETED)

    def test_void_sales_grant_allows_voiding_sale(self):
        void_permission, _ = SpecialPermission.objects.get_or_create(
            code='can_void_sales',
            defaults={'name': 'Void Sales'},
        )
        self.role.special_permissions.create(permission=void_permission)

        detail_response = self.client.get(
            reverse('pos:sale_detail', args=[self.sale.pk]),
        )
        self.assertContains(detail_response, 'Void Sale')

        response = self.client.post(
            reverse('pos:void_sale', args=[self.sale.pk]),
            {'reason': 'Authorized void'},
        )

        self.assertRedirects(response, reverse('pos:sales_list'))
        self.sale.refresh_from_db()
        self.assertEqual(self.sale.status, Sale.Status.VOIDED)
        self.assertEqual(self.sale.void_reason, 'Authorized void')

    def test_pos_user_cannot_void_or_view_sales_from_another_branch(self):
        void_permission, _ = SpecialPermission.objects.get_or_create(
            code='can_void_sales',
            defaults={'name': 'Void Sales'},
        )
        self.role.special_permissions.create(permission=void_permission)
        other_branch = Branch.objects.create(name='Other Sale Branch')
        other_sale = Sale.objects.create(
            branch=other_branch,
            cashier=self.user,
            status=Sale.Status.COMPLETED,
            subtotal=50,
            total=50,
            amount_paid=50,
        )

        for route_name in ('pos:sale_detail', 'pos:receipt'):
            with self.subTest(route=route_name):
                response = self.client.get(
                    reverse(route_name, args=[other_sale.pk]),
                )
                self.assertEqual(response.status_code, 404)

        response = self.client.post(
            reverse('pos:void_sale', args=[other_sale.pk]),
            {'reason': 'Cross-branch attempt'},
        )

        self.assertEqual(response.status_code, 404)
        other_sale.refresh_from_db()
        self.assertEqual(other_sale.status, Sale.Status.COMPLETED)

    def test_refund_approval_actions_are_hidden_and_branch_scoped(self):
        local_refund = Refund.objects.create(
            sale=self.sale,
            amount=50,
            reason='Local refund control test',
            requested_by=self.user,
        )
        other_branch = Branch.objects.create(name='Other Refund Branch')
        other_sale = Sale.objects.create(
            branch=other_branch,
            cashier=self.user,
            status=Sale.Status.COMPLETED,
            subtotal=50,
            total=50,
            amount_paid=50,
        )
        refund = Refund.objects.create(
            sale=other_sale,
            amount=50,
            reason='Cross-branch refund test',
            requested_by=self.user,
        )

        list_response = self.client.get(reverse('pos:refund_list'))
        self.assertEqual(list_response.status_code, 200)
        self.assertContains(list_response, local_refund.refund_id)
        self.assertNotContains(list_response, 'title="Approve"')

        approve_permission, _ = SpecialPermission.objects.get_or_create(
            code='can_approve_refunds',
            defaults={'name': 'Approve Refunds'},
        )
        self.role.special_permissions.create(permission=approve_permission)

        list_response = self.client.get(reverse('pos:refund_list'))
        self.assertContains(list_response, 'title="Approve"')

        for route_name in (
            'pos:refund_approve',
            'pos:refund_complete',
            'pos:refund_reject',
        ):
            with self.subTest(route=route_name):
                response = self.client.post(
                    reverse(route_name, args=[refund.pk]),
                )
                self.assertEqual(response.status_code, 404)

        refund.refresh_from_db()
        self.assertEqual(refund.status, Refund.Status.PENDING)

        local_response = self.client.post(
            reverse('pos:refund_approve', args=[local_refund.pk]),
        )
        self.assertRedirects(local_response, reverse('pos:refund_list'))
        local_refund.refresh_from_db()
        self.assertEqual(local_refund.status, Refund.Status.APPROVED)

    def test_pos_requires_assigned_branch_and_rejects_other_branch_item_filters(self):
        other_branch = Branch.objects.create(name='Other POS Item Branch')
        product = Product.objects.create(
            name='Other Branch Product',
            item_type='Product',
            branch=other_branch,
            price=10,
            stock_quantity=5,
        )

        filter_response = self.client.get(
            reverse('pos:filter_items'),
            {'branch_id': other_branch.pk},
        )
        self.assertEqual(filter_response.status_code, 403)
        self.assertNotContains(
            self.client.get(reverse('pos:search_items'), {'q': product.name}),
            product.name,
        )

        self.user.branch = None
        self.user.save(update_fields=['branch'])

        checkout_response = self.client.get(reverse('pos:checkout'))
        self.assertRedirects(
            checkout_response,
            reverse('accounts:select_branch'),
        )
        unassigned_filter_response = self.client.get(
            reverse('pos:filter_items'),
        )
        self.assertEqual(unassigned_filter_response.status_code, 403)
