from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from billing.models import CustomerStatement


@override_settings(
    STORAGES={
        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
        'staticfiles': {
            'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage',
        },
    }
)
class CustomerStatementPortalTests(TestCase):
    def test_pet_owner_cannot_open_service_management_url(self):
        owner = get_user_model().objects.create_user(
            username='service-list-unauthorized-owner',
            email='service-list-unauthorized-owner@example.com',
            password='A-secure-test-password-935!',
        )
        self.client.force_login(owner)

        response = self.client.get(reverse('billing:billable_items'))

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('accounts:user_dashboard'))

    def test_statement_cards_keep_view_and_print_actions_with_updated_layout(self):
        owner = get_user_model().objects.create_user(
            username='soa-card-owner',
            email='soa-card-owner@example.com',
            password='A-secure-test-password-923!',
        )
        statement = CustomerStatement.objects.create(
            patient_name='Milo',
            owner_name='SOA Card Owner',
            customer=owner,
            date=date(2026, 10, 13),
            total_amount=1500,
            deposit=500,
            status='RELEASED',
        )
        self.client.force_login(owner)

        response = self.client.get(reverse('billing:my_statements'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'soa-identity')
        self.assertContains(response, 'bx-receipt')
        self.assertContains(response, 'Issued Oct 13, 2026')
        self.assertContains(response, 'Milo')
        self.assertContains(response, '₱1,500.00')
        self.assertContains(response, '₱1,000.00')
        self.assertContains(
            response,
            reverse('billing:my_statement_detail', args=[statement.pk]),
        )
        self.assertContains(
            response,
            f'{reverse("billing:my_statement_detail", args=[statement.pk])}?format=print',
        )
