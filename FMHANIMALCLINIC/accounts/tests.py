import re
from urllib.parse import parse_qs, urlsplit

from django.contrib.auth import get_user_model
from django.core import mail
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse

from .forms import PetOwnerRegistrationForm


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class RegistrationEmailVerificationTests(TestCase):
    def registration_data(self, email):
        return {
            'username': 'newpetowner',
            'first_name': 'New',
            'last_name': 'Owner',
            'email': email,
            'phone_number': '09123456789',
            'address': '',
            'password1': 'A-secure-test-password-923!',
            'password2': 'A-secure-test-password-923!',
            'terms': 'on',
        }

    def test_registration_sends_verify_now_link_and_link_verifies_email(self):
        response = self.client.post(
            reverse('accounts:register_page'),
            self.registration_data('owner@example.com'),
        )

        self.assertEqual(response.status_code, 302)
        user = get_user_model().objects.get(username='newpetowner')
        self.assertFalse(user.email_verified)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['owner@example.com'])
        self.assertIn('Verify now', mail.outbox[0].alternatives[0][0])

        verification_url = re.search(r'https?://\S+', mail.outbox[0].body).group(0)
        token = parse_qs(urlsplit(verification_url).query)['token'][0]
        response = self.client.get(reverse('accounts:verify_email'), {'token': token})

        user.refresh_from_db()
        self.assertTrue(user.email_verified)
        self.assertEqual(response.status_code, 302)

    def test_registration_rejects_case_insensitive_duplicate_email(self):
        get_user_model().objects.create_user(
            username='existingowner',
            email='owner@example.com',
            password='A-secure-test-password-923!',
        )
        form = PetOwnerRegistrationForm(
            self.registration_data('OWNER@example.com')
        )

        self.assertFalse(form.is_valid())
        self.assertIn('email', form.errors)

    def test_profile_email_edit_checks_existing_addresses_case_insensitively(self):
        existing_user = get_user_model().objects.create_user(
            username='existingowner',
            email='owner@example.com',
            password='A-secure-test-password-923!',
        )
        editing_user = get_user_model().objects.create_user(
            username='editingowner',
            email='editing@example.com',
            password='A-secure-test-password-923!',
        )
        from .forms import UserProfileUpdateForm

        form = UserProfileUpdateForm(
            data={
                'username': editing_user.username,
                'first_name': '',
                'last_name': '',
                'email': existing_user.email.upper(),
                'phone_number': '',
                'address': '',
                'branch': '',
            },
            instance=editing_user,
        )

        self.assertFalse(form.is_valid())
        self.assertIn('email', form.errors)

    def test_new_users_are_unverified_by_default(self):
        user = get_user_model().objects.create_user(
            username='pendingowner',
            email='pending@example.com',
            password='A-secure-test-password-923!',
        )

        self.assertFalse(user.email_verified)

    def test_database_rejects_case_insensitive_duplicate_emails(self):
        get_user_model().objects.create_user(
            username='existingowner',
            email='owner@example.com',
            password='A-secure-test-password-923!',
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                get_user_model().objects.create_user(
                    username='duplicateowner',
                    email='OWNER@example.com',
                    password='A-secure-test-password-923!',
                )