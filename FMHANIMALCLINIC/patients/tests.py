from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from .forms import AdminPetForm


class AdminPetWalkInContactTests(TestCase):
    def setUp(self):
        self.form_data = {
            'source': 'WALKIN',
            'guest_owner_name': 'Walk-in Owner',
            'guest_owner_phone': '09123456789',
            'guest_owner_email': 'owner@example.com',
            'name': 'Buddy',
            'species': 'Dog',
            'sex': 'MALE',
        }

    def test_walkin_patient_requires_phone_number(self):
        form_data = self.form_data.copy()
        form_data['guest_owner_phone'] = ''

        form = AdminPetForm(data=form_data)

        self.assertFalse(form.is_valid())
        self.assertIn('guest_owner_phone', form.errors)

    def test_walkin_patient_requires_email_address(self):
        form_data = self.form_data.copy()
        form_data['guest_owner_email'] = ''

        form = AdminPetForm(data=form_data)

        self.assertFalse(form.is_valid())
        self.assertIn('guest_owner_email', form.errors)

    def test_walkin_patient_accepts_valid_contact_details(self):
        form = AdminPetForm(data=self.form_data)

        self.assertTrue(form.is_valid(), form.errors)


class PortalOwnerSearchTests(TestCase):
    def test_owner_search_matches_phone_number(self):
        admin = get_user_model().objects.create_superuser(
            username='patientadmin',
            email='patientadmin@example.com',
            password='A-secure-test-password-923!',
        )
        owner = get_user_model().objects.create_user(
            username='portalowner',
            email='owner@example.com',
            phone_number='09123456789',
            first_name='Portal',
            last_name='Owner',
            password='A-secure-test-password-924!',
        )
        client = Client()
        client.force_login(admin)

        response = client.get(
            reverse('patients:api_owner_search'),
            {'q': '091234'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['owners'][0]['id'], owner.pk)
        self.assertEqual(response.json()['owners'][0]['phone'], '09123456789')
