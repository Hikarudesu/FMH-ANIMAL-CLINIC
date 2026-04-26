from django.test import RequestFactory, TestCase

from settings.context_processors import clinic_settings
from settings.forms import ClinicInfoForm
from settings.models import ClinicProfile, LegalDocument


class ClinicInfoTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_clinic_profile_is_singleton(self):
        first = ClinicProfile.get_instance()
        second = ClinicProfile.get_instance()

        self.assertEqual(first.pk, 1)
        self.assertEqual(second.pk, 1)
        self.assertEqual(ClinicProfile.objects.count(), 1)

    def test_clinic_info_form_saves_profile_and_legal_docs(self):
        profile = ClinicProfile.get_instance()

        form = ClinicInfoForm(
            data={
                "name": "FMH Animal Clinic",
                "email": "clinic@example.com",
                "phone": "09123456789",
                "address": "123 Test St",
                "license_number": "LIC-001",
                "tos_content": "Terms content",
                "privacy_policy_content": "Privacy content",
            },
            instance=profile,
        )

        self.assertTrue(form.is_valid(), form.errors)
        form.save()

        updated = ClinicProfile.get_instance()
        self.assertEqual(updated.email, "clinic@example.com")
        self.assertEqual(updated.phone, "09123456789")
        self.assertEqual(updated.address, "123 Test St")

        tos = LegalDocument.get_tos()
        privacy = LegalDocument.get_privacy_policy()
        self.assertIsNotNone(tos)
        self.assertIsNotNone(privacy)
        self.assertEqual(tos.content, "Terms content")
        self.assertEqual(privacy.content, "Privacy content")

    def test_clinic_info_form_rejects_invalid_phone(self):
        profile = ClinicProfile.get_instance()

        form = ClinicInfoForm(
            data={
                "name": "FMH Animal Clinic",
                "email": "",
                "phone": "1234",
                "address": "",
                "license_number": "",
                "tos_content": "",
                "privacy_policy_content": "",
            },
            instance=profile,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("phone", form.errors)

    def test_clinic_settings_context_processor_returns_profile_values(self):
        profile = ClinicProfile.get_instance()
        profile.name = "FMH Animal Clinic"
        profile.email = "contact@example.com"
        profile.phone = "09123456789"
        profile.address = "Sample Address"
        profile.save()

        context = clinic_settings(self.factory.get("/"))

        self.assertEqual(context["CLINIC_NAME"], "FMH Animal Clinic")
        self.assertEqual(context["CLINIC_EMAIL"], "contact@example.com")
        self.assertEqual(context["CLINIC_PHONE"], "09123456789")
        self.assertEqual(context["CLINIC_ADDRESS"], "Sample Address")
        self.assertEqual(context["CURRENCY"], "PHP")
        self.assertNotIn("CLINIC_TITLE", context)
        self.assertNotIn("CLINIC_SLOGAN", context)
        self.assertNotIn("CLINIC_HERO_DESCRIPTION", context)
