from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.rbac_models import Module, ModulePermission, Role
from branches.models import Branch
from patients.models import Pet

from .models import AIDiagnosis, AIDiagnosisRateLimit
from .services import (
    AI_HISTORY_MAX_CHARS,
    _SYSTEM_PROMPT,
    _build_history_text,
    get_ai_diagnosis,
)
from .views import AI_DIAGNOSIS_REQUESTS_PER_HOUR


User = get_user_model()


class AIDiagnosticsSecurityTests(TestCase):
    def setUp(self):
        self.branch = Branch.objects.create(
            name='AI Scope Branch',
            phone_number='09123456789',
            address='1 Test Street',
            city='Test City',
            state='Test State',
            zip_code='1000',
        )
        self.other_branch = Branch.objects.create(
            name='Other AI Branch',
            phone_number='09123456788',
            address='2 Test Street',
            city='Test City',
            state='Test State',
            zip_code='1000',
        )
        module, _ = Module.objects.get_or_create(
            code='ai_diagnostics', defaults={'name': 'AI Diagnostics'},
        )
        role = Role.objects.create(
            name='AI Branch Staff',
            code='ai-branch-staff',
            hierarchy_level=2,
            is_staff_role=True,
        )
        for permission_type in (
            ModulePermission.PermissionType.VIEW,
            ModulePermission.PermissionType.CREATE,
            ModulePermission.PermissionType.DELETE,
        ):
            ModulePermission.objects.create(
                role=role,
                module=module,
                permission_type=permission_type,
                restrict_to_branch=True,
            )
        self.staff = User.objects.create_user(
            username='ai-branch-staff',
            password='A-secure-test-password-923!',
            assigned_role=role,
            branch=self.branch,
        )
        self.foreign_pet = Pet.objects.create(
            name='Other Branch Pet',
            species='Dog',
            sex=Pet.Sex.MALE,
            branch=self.other_branch,
        )
        self.diagnosis = AIDiagnosis.objects.create(
            pet=self.foreign_pet,
            primary_condition='Test condition',
        )

    def test_branch_restricted_staff_cannot_access_another_branch_ai_data(self):
        self.client.force_login(self.staff)
        urls = (
            reverse('diagnostics:run_diagnosis', args=[self.foreign_pet.pk]),
            reverse('diagnostics:detail', args=[self.diagnosis.pk]),
            reverse('diagnostics:pet_history', args=[self.foreign_pet.pk]),
        )

        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 404)

        self.assertEqual(
            self.client.post(
                reverse('diagnostics:mark_reviewed', args=[self.diagnosis.pk]),
                {'selected_condition': 'Test condition', 'vet_prescription': 'Test'},
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                reverse('diagnostics:delete', args=[self.diagnosis.pk]),
            ).status_code,
            404,
        )
        self.assertTrue(AIDiagnosis.objects.filter(pk=self.diagnosis.pk).exists())

    def test_branch_restricted_staff_without_a_branch_get_no_ai_pet_access(self):
        self.staff.branch = None
        self.staff.save(update_fields=['branch'])
        self.client.force_login(self.staff)

        response = self.client.get(
            reverse('diagnostics:run_diagnosis', args=[self.foreign_pet.pk]),
        )

        self.assertEqual(response.status_code, 404)

    def test_ai_requests_are_limited_before_calling_groq(self):
        admin = User.objects.create_superuser(
            username='ai-rate-limit-admin',
            email='ai-rate-limit-admin@example.com',
            password='A-secure-test-password-924!',
        )
        pet = Pet.objects.create(
            name='Rate Limit Pet',
            species='Dog',
            sex=Pet.Sex.FEMALE,
            branch=self.branch,
        )
        self.client.force_login(admin)
        result = {
            'primary_diagnosis': {'condition': 'Test condition', 'reasoning': 'Test'},
            'differential_diagnoses': [],
            'recommended_tests': [],
            'warning_signs': [],
            'summary': 'Test result',
        }

        with patch('diagnostics.views.get_ai_diagnosis', return_value=result) as ai_call:
            for _ in range(AI_DIAGNOSIS_REQUESTS_PER_HOUR):
                response = self.client.post(
                    reverse('diagnostics:run_diagnosis', args=[pet.pk]),
                    {'current_symptoms': 'Cough'},
                )
                self.assertEqual(response.status_code, 302)

            response = self.client.post(
                reverse('diagnostics:run_diagnosis', args=[pet.pk]),
                {'current_symptoms': 'Cough'},
            )

        self.assertEqual(response.status_code, 429)
        self.assertGreater(int(response['Retry-After']), 0)
        self.assertEqual(ai_call.call_count, AI_DIAGNOSIS_REQUESTS_PER_HOUR)
        self.assertEqual(
            AIDiagnosisRateLimit.objects.filter(user=admin).get().request_count,
            AI_DIAGNOSIS_REQUESTS_PER_HOUR,
        )

    def test_oversized_symptoms_do_not_call_groq_or_consume_quota(self):
        admin = User.objects.create_superuser(
            username='ai-payload-admin',
            email='ai-payload-admin@example.com',
            password='A-secure-test-password-925!',
        )
        self.client.force_login(admin)

        with patch('diagnostics.views.get_ai_diagnosis') as ai_call:
            response = self.client.post(
                reverse('diagnostics:run_diagnosis', args=[self.foreign_pet.pk]),
                {'current_symptoms': 'x' * 4001},
            )

        self.assertEqual(response.status_code, 400)
        ai_call.assert_not_called()
        self.assertFalse(AIDiagnosisRateLimit.objects.filter(user=admin).exists())

    def test_groq_failure_is_shown_without_saving_a_diagnosis(self):
        pet = Pet.objects.create(
            name='AI Service Failure Pet',
            species='Dog',
            sex=Pet.Sex.FEMALE,
            branch=self.branch,
        )
        self.client.force_login(self.staff)

        with patch(
            'diagnostics.views.get_ai_diagnosis',
            return_value={
                'primary_diagnosis': {'condition': 'Unable to determine'},
                '_error': True,
            },
        ):
            response = self.client.post(
                reverse('diagnostics:run_diagnosis', args=[pet.pk]),
                {'current_symptoms': 'Nagsusuka at ayaw kumain'},
            )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'AI diagnosis service is currently unavailable')
        self.assertContains(response, 'Nagsusuka at ayaw kumain')
        self.assertFalse(AIDiagnosis.objects.filter(pet=pet).exists())

    def test_prompt_handles_tagalog_typos_and_english_output(self):
        self.assertIn('Filipino/Tagalog', _SYSTEM_PROMPT)
        self.assertIn('Taglish', _SYSTEM_PROMPT)
        self.assertIn('spelling and spacing errors', _SYSTEM_PROMPT)
        self.assertIn('in clear English', _SYSTEM_PROMPT)

    @patch('diagnostics.services._attempt_groq_call')
    @patch('diagnostics.services._get_groq_api_key', return_value='test-key')
    def test_current_symptoms_are_a_prioritized_prompt_section(
        self, _get_api_key, groq_call,
    ):
        history_entry = SimpleNamespace(
            action_required=SimpleNamespace(name='Follow up'),
            date_recorded=date(2026, 10, 10),
            weight=12,
            temperature=39,
            history_clinical_signs='Nagsusuka at matamlay',
            treatment='Oral fluids and monitoring',
            rx='Medication prescribed',
        )
        groq_call.return_value = {
            'primary_diagnosis': {
                'condition': 'Test condition',
                'reasoning': 'Test reasoning',
            },
            'differential_diagnoses': [],
            'recommended_tests': [],
            'warning_signs': [],
            'summary': 'Test summary',
        }

        get_ai_diagnosis(
            pet=self.foreign_pet,
            record_entries=[history_entry],
            additional_symptoms='Nagsusuka at ayaw kumain',
        )

        prompt = groq_call.call_args.args[1]
        self.assertIn('Current Symptoms / Clinical Signs (prioritized presenting complaint):', prompt)
        self.assertIn('Nagsusuka at ayaw kumain', prompt)
        self.assertIn('Pet Information:', prompt)
        self.assertIn('Species: Dog', prompt)
        self.assertIn('Medical Visit History (all supplied entries; clinical context):', prompt)
        self.assertIn('Nagsusuka at matamlay', prompt)
        self.assertIn('Oral fluids and monitoring', prompt)
        self.assertIn('explicitly name relevant symptoms', _SYSTEM_PROMPT)
        self.assertIn('Review the pet\'s supplied species, breed, age, sex, and clinical status', _SYSTEM_PROMPT)

    @patch('diagnostics.services._attempt_groq_call')
    @patch('diagnostics.services._get_groq_api_key', return_value='test-key')
    def test_medical_history_is_used_when_current_symptoms_are_empty(
        self, _get_api_key, groq_call,
    ):
        groq_call.return_value = {
            'primary_diagnosis': {
                'condition': 'Test condition',
                'reasoning': 'Based on recorded visit history',
            },
            'differential_diagnoses': [],
            'recommended_tests': [],
            'warning_signs': [],
            'summary': 'Assessment based on recorded history.',
        }
        history_entry = SimpleNamespace(
            action_required=None,
            date_recorded=date(2026, 10, 10),
            weight=None,
            temperature=None,
            history_clinical_signs='Previously recorded recurring cough',
            treatment='Prior supportive care',
            rx='',
        )

        get_ai_diagnosis(
            pet=self.foreign_pet,
            record_entries=[history_entry],
        )

        prompt = groq_call.call_args.args[1]
        self.assertIn('Current Symptoms / Clinical Signs (prioritized presenting complaint):\nNone provided.', prompt)
        self.assertIn('Previously recorded recurring cough', prompt)
        self.assertIn('Prior supportive care', prompt)
        self.assertIn('If no current symptoms are provided', _SYSTEM_PROMPT)
        self.assertIn('Base the assessment on the pet information and all', _SYSTEM_PROMPT)

    def test_clinical_history_prompt_has_a_fixed_character_limit(self):
        entry = SimpleNamespace(
            action_required=None,
            date_recorded=date.today(),
            weight=None,
            temperature=None,
            history_clinical_signs='x' * (AI_HISTORY_MAX_CHARS + 100),
            treatment='',
            rx='',
        )

        history_text = _build_history_text([entry])

        self.assertEqual(len(history_text), AI_HISTORY_MAX_CHARS)
        self.assertTrue(history_text.endswith('[Older clinical history truncated.]'))

    def test_clinical_history_preserves_tagalog_and_taglish_text(self):
        entry = SimpleNamespace(
            action_required=None,
            date_recorded=date.today(),
            weight=None,
            temperature=None,
            history_clinical_signs='Nagsusuka at ayaw kumain, parang matamlay',
            treatment='Bigyan ng fluids; monitor kung nagsusuka pa',
            rx='',
        )

        history_text = _build_history_text([entry])

        self.assertIn('Nagsusuka at ayaw kumain', history_text)
        self.assertIn('monitor kung nagsusuka pa', history_text)