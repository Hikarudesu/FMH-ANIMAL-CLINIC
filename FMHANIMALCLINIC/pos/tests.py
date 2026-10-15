from datetime import time

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from appointments.models import Appointment
from branches.models import Branch
from pos.models import Sale


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
        self.appointment.refresh_from_db()
        self.assertIsNotNone(self.appointment.sale_id)
        self.assertEqual(self.appointment.sale.branch_id, self.branch.pk)
        self.assertEqual(self.appointment.sale.cashier_id, self.cashier.pk)
        self.assertEqual(self.appointment.sale.status, 'PENDING')

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
