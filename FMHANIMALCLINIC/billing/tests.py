from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from billing.forms import ServiceForm
from billing.models import CustomerStatement, Service


class ClinicServiceTaxRemovalTests(TestCase):
    def test_service_form_and_model_do_not_expose_tax_rate(self):
        self.assertNotIn('tax_rate', ServiceForm().fields)
        self.assertNotIn('tax_rate', {field.name for field in Service._meta.fields})

    def test_service_can_be_created_without_tax_rate(self):
        service = Service.objects.create(name='Dental Cleaning', price=1500)

        self.assertEqual(service.name, 'Dental Cleaning')
        self.assertEqual(service.price, 1500)


@override_settings(
    STORAGES={
        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
        'staticfiles': {
            'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage',
        },
    }
)
class ClinicServiceDeleteConfirmationTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser(
            username='clinic-service-delete-admin',
            email='clinic-service-delete-admin@example.com',
            password='A-secure-test-password-947!',
        )
        self.service = Service.objects.create(
            name='Confirmation Test Service',
            price=500,
        )
        self.client.force_login(self.admin)

    def test_service_delete_uses_inventory_confirmation_flow_and_requires_post(self):
        response = self.client.get(reverse('billing:billable_items'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="deleteServiceModal"')
        self.assertContains(response, 'id="finalDeleteServiceModal"')
        self.assertContains(response, 'requestFinalServiceDeleteConfirmation(event)')
        self.assertContains(response, 'confirmFinalServiceDelete()')
        self.assertNotContains(response, 'window.showCenteredConfirmation')
        self.assertContains(response, 'id="deleteServiceForm" method="post"')
        self.assertContains(response, 'csrfmiddlewaretoken')

        get_response = self.client.get(
            reverse('billing:billable_item_delete', args=[self.service.pk]),
        )
        self.assertRedirects(get_response, reverse('billing:billable_items'))
        self.assertTrue(Service.objects.filter(pk=self.service.pk).exists())

        post_response = self.client.post(
            reverse('billing:billable_item_delete', args=[self.service.pk]),
        )
        self.assertRedirects(post_response, reverse('billing:billable_items'))
        self.assertFalse(Service.objects.filter(pk=self.service.pk).exists())


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
        self.assertContains(response, 'Account Date')
        self.assertContains(response, 'Oct 13, 2026')
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

    def test_statement_card_content_breakdown_and_general_services_handling(self):
        owner = get_user_model().objects.create_user(
            username='otc-buyer-owner',
            email='otc-buyer-owner@example.com',
            password='A-secure-test-password-923!',
        )
        # Statement with General Services (retail / walk-in product purchase)
        otc_statement = CustomerStatement.objects.create(
            patient_name='General Services',
            owner_name='OTC Buyer',
            customer=owner,
            date=date(2026, 10, 15),
            total_amount=850,
            deposit=850,
            status='RELEASED',
        )

        self.client.force_login(owner)
        response = self.client.get(reverse('billing:my_statements'))

        self.assertEqual(response.status_code, 200)
        # Should display Purchase Type: Retail / OTC
        self.assertContains(response, 'Purchase Type')
        self.assertContains(response, 'Retail / OTC')
        # Should NOT display "Patient" for General Services
        self.assertNotContains(response, '<span class="label">Patient</span>')

