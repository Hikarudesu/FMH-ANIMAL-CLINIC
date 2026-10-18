from datetime import time

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from appointments.models import Appointment
from branches.models import Branch
from inventory.models import Product
from pos.models import Payment, Sale, SaleItem
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
