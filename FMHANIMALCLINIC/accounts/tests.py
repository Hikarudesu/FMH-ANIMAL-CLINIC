import re
from urllib.parse import parse_qs, urlsplit

from dateutil.relativedelta import relativedelta
from django.contrib.auth import get_user_model
from django.core import mail
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .forms import PetOwnerRegistrationForm
from .lifecycle import (
    expire_due_owner_accounts,
    resolve_owner_deactivation_on_login,
    schedule_owner_deactivation,
)


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


class OwnerAccountDeactivationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='petowner',
            email='petowner@example.com',
            password='A-secure-test-password-923!',
        )

    def test_owner_has_one_month_to_cancel_by_logging_in(self):
        now = timezone.now()
        schedule_owner_deactivation(self.user, now=now)

        self.user.refresh_from_db()
        self.assertEqual(
            self.user.owner_deactivation_due_at,
            now + relativedelta(months=1),
        )
        self.assertEqual(resolve_owner_deactivation_on_login(self.user, now=now + relativedelta(days=2)), 'cancelled')

        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)
        self.assertIsNone(self.user.owner_deactivation_due_at)

    def test_due_owner_is_deactivated_but_account_is_retained(self):
        now = timezone.now()
        self.user.owner_deactivation_requested_at = now - relativedelta(months=1)
        self.user.owner_deactivation_due_at = now - relativedelta(seconds=1)
        self.user.save(update_fields=[
            'owner_deactivation_requested_at',
            'owner_deactivation_due_at',
        ])

        self.assertEqual(expire_due_owner_accounts(now=now), 1)

        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)
        self.assertEqual(self.user.owner_account_deactivated_at, now)
        self.assertTrue(get_user_model().objects.filter(pk=self.user.pk).exists())

    def test_overdue_login_expires_instead_of_cancelling(self):
        now = timezone.now()
        self.user.owner_deactivation_due_at = now - relativedelta(seconds=1)
        self.user.save(update_fields=['owner_deactivation_due_at'])

        self.assertEqual(resolve_owner_deactivation_on_login(self.user, now=now), 'expired')
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)

    def test_profile_request_schedules_account_deactivation(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse('accounts:request_owner_deactivation'),
            {'confirm_deactivation': 'on'},
        )

        self.user.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertTrue(self.user.is_active)
        self.assertIsNotNone(self.user.owner_deactivation_due_at)

    def test_pet_owner_login_before_due_date_cancels_schedule(self):
        schedule_owner_deactivation(self.user)

        response = self.client.post(reverse('accounts:login_page'), {
            'username': self.user.username,
            'password': 'A-secure-test-password-923!',
        })

        self.user.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertTrue(self.user.is_active)
        self.assertIsNone(self.user.owner_deactivation_due_at)

    def test_superadmin_archive_displays_retained_pet_and_medical_record(self):
        from patients.models import Pet
        from records.models import MedicalRecord

        now = timezone.now()
        self.user.is_active = False
        self.user.owner_account_deactivated_at = now
        self.user.save(update_fields=['is_active', 'owner_account_deactivated_at'])
        pet = Pet.objects.create(
            owner=self.user,
            name='Archive Companion',
            species='Dog',
            sex=Pet.Sex.MALE,
        )
        MedicalRecord.objects.bulk_create([
            MedicalRecord(pet=pet, date_recorded=now.date()),
        ])
        superadmin = get_user_model().objects.create_superuser(
            username='archiveadmin',
            email='archiveadmin@example.com',
            password='A-secure-test-password-923!',
        )
        self.client.force_login(superadmin)

        response = self.client.get(reverse('accounts:owner_archive'), {'q': 'Archive Companion'})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Pet Owner Archive')
        self.assertContains(response, 'Archive Companion')
        self.assertContains(response, 'Medical record')
        self.assertTrue(get_user_model().objects.filter(pk=self.user.pk).exists())