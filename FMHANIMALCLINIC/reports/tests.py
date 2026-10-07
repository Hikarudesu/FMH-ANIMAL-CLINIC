from decimal import Decimal
from datetime import time

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from appointments.models import Appointment
from branches.models import Branch
from patients.models import Pet
from pos.models import Sale


class AnalyticsDashboardTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser(
            username='analytics-test-admin',
            email='analytics-test-admin@example.com',
            password='A-secure-test-password-923!',
        )
        self.client.force_login(self.admin)
        self.branch_a = self.create_branch('Analytics Branch A')
        self.branch_b = self.create_branch('Analytics Branch B')

    def create_branch(self, name):
        return Branch.objects.create(
            name=name,
            phone_number='09123456789',
            address='1 Test Street',
            city='Test City',
            state='Test State',
            zip_code='1000',
        )

    def test_daily_branch_filter_scopes_patients_sales_and_appointments(self):
        Pet.objects.create(
            name='Branch A Pet', species='Dog', sex=Pet.Sex.MALE,
            branch=self.branch_a,
        )
        Pet.objects.create(
            name='Branch B Pet', species='Cat', sex=Pet.Sex.FEMALE,
            branch=self.branch_b,
        )
        Sale.objects.create(
            branch=self.branch_a,
            subtotal=Decimal('100.00'),
            discount_percent=Decimal('10.00'),
            total=Decimal('90.00'),
            status=Sale.Status.COMPLETED,
        )
        Sale.objects.create(
            branch=self.branch_b,
            subtotal=Decimal('300.00'),
            total=Decimal('300.00'),
            status=Sale.Status.COMPLETED,
        )
        Appointment.objects.create(
            owner_name='Branch A Owner', pet_name='Branch A Pet',
            branch=self.branch_a, appointment_date=timezone.localdate(),
            appointment_time=time(10), is_returning_customer=False,
        )
        Appointment.objects.create(
            owner_name='Branch B Owner', pet_name='Branch B Pet',
            branch=self.branch_b, appointment_date=timezone.localdate(),
            appointment_time=time(11), is_returning_customer=True,
        )

        response = self.client.get(reverse('reports:analytics_dashboard'), {
            'period': 'daily',
            'branch': str(self.branch_a.pk),
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['total_patients'], 1)
        self.assertEqual(response.context['new_patients_period'], 1)
        self.assertEqual(response.context['gross_sales'], Decimal('100.00'))
        self.assertEqual(response.context['net_sales'], Decimal('90.00'))
        self.assertEqual(response.context['total_discount'], Decimal('10.00'))
        self.assertEqual(response.context['transaction_count'], 1)
        self.assertEqual(response.context['new_clients'], 1)
        self.assertEqual(response.context['returning_clients'], 0)
