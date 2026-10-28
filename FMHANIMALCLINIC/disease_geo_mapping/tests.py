from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from accounts.rbac_models import (
    Module,
    ModulePermission,
    Role,
    RoleSpecialPermission,
    SpecialPermission,
    SpecialPermissionCodes,
)
from branches.models import Branch
from disease_geo_mapping.services import summarize_branch_disease_trends
from disease_geo_mapping.views import _get_analysis_date_range
from patients.models import Pet
from records.models import MedicalRecord, RecordEntry


class AnalysisDateRangeTests(SimpleTestCase):
    def test_defaults_to_the_previous_six_calendar_months(self):
        today = date(2026, 10, 20)

        earliest_date, start_date, end_date = _get_analysis_date_range('', '', today)

        self.assertEqual(earliest_date, date(2026, 4, 20))
        self.assertEqual(start_date, earliest_date)
        self.assertEqual(end_date, today)

    def test_clamps_dates_outside_the_allowed_window(self):
        today = date(2026, 10, 20)

        earliest_date, start_date, end_date = _get_analysis_date_range(
            '2025-01-01', '2027-01-01', today,
        )

        self.assertEqual(start_date, earliest_date)
        self.assertEqual(end_date, today)

    def test_corrects_a_reversed_date_range(self):
        today = date(2026, 10, 20)

        _, start_date, end_date = _get_analysis_date_range(
            '2026-10-10', '2026-10-01', today,
        )

        self.assertEqual(start_date, end_date)
        self.assertEqual(end_date, date(2026, 10, 1))


class DiseaseVisitAggregationTests(TestCase):
    def setUp(self):
        self.branch = Branch.objects.create(
            name='Geo Mapping Test Branch',
            phone_number='09123456789',
            address='1 Test Street',
            city='Test City',
            state='Test State',
            zip_code='1000',
        )

    def test_aggregates_every_matching_visit_and_distinct_pet(self):
        visit_date = date(2026, 10, 20)
        pets = [
            Pet.objects.create(
                name='Geo Test Dog', species='Dog', breed='Labrador',
                sex=Pet.Sex.MALE, branch=self.branch,
            ),
            Pet.objects.create(
                name='Geo Test Cat', species='Cat', breed='Siamese',
                sex=Pet.Sex.FEMALE, branch=self.branch,
            ),
        ]
        records = [
            MedicalRecord.objects.create(
                pet=pet, branch=self.branch, date_recorded=visit_date,
            )
            for pet in pets
        ]
        RecordEntry.objects.bulk_create([
            RecordEntry(
                record=records[index % 2],
                date_recorded=visit_date,
                history_clinical_signs='Persistent cough',
                treatment='Supportive care',
                rx='Medication as prescribed',
            )
            for index in range(501)
        ])

        result = summarize_branch_disease_trends(
            self.branch,
            start_date=visit_date - timedelta(days=1),
            end_date=visit_date,
        )

        self.assertEqual(result['total_cases'], 501)
        self.assertEqual(result['medical_record_count'], 2)
        prediction = result['disease_counts'][0]
        self.assertEqual(prediction['value'], 501)
        self.assertEqual(prediction['distinct_pets'], 2)
        self.assertNotIn('pet_profile_summary', prediction)

    def test_unmatched_visit_does_not_create_a_fake_disease_prediction(self):
        pet = Pet.objects.create(
            name='Unmatched Visit Pet', species='Dog', sex=Pet.Sex.MALE,
            branch=self.branch,
        )
        record = MedicalRecord.objects.create(
            pet=pet, branch=self.branch, date_recorded=date(2026, 10, 20),
        )
        RecordEntry.objects.create(
            record=record,
            date_recorded=date(2026, 10, 20),
            history_clinical_signs='Routine follow-up; no specific symptoms recorded',
        )

        result = summarize_branch_disease_trends(
            self.branch,
            start_date=date(2026, 10, 1),
            end_date=date(2026, 10, 20),
        )

        self.assertEqual(result['total_cases'], 1)
        self.assertEqual(result['disease_counts'], [])
        self.assertIn('No supported disease pattern', result['summary'])

    def test_visit_total_includes_unmatched_history_without_predicting_it(self):
        pets = [
            Pet.objects.create(
                name=f'Mixed History Pet {index}',
                species='Dog',
                sex=Pet.Sex.MALE,
                branch=self.branch,
            )
            for index in range(3)
        ]
        for index, pet in enumerate(pets):
            record = MedicalRecord.objects.create(
                pet=pet, branch=self.branch, date_recorded=date(2026, 10, 20),
            )
            RecordEntry.objects.create(
                record=record,
                date_recorded=date(2026, 10, 20),
                history_clinical_signs=(
                    'Persistent cough' if index < 2 else 'Routine follow-up'
                ),
            )

        result = summarize_branch_disease_trends(
            self.branch,
            start_date=date(2026, 10, 1),
            end_date=date(2026, 10, 20),
        )

        self.assertEqual(result['total_cases'], 3)
        self.assertEqual(len(result['disease_counts']), 1)
        self.assertEqual(result['disease_counts'][0]['value'], 2)

    def test_visit_from_another_record_branch_is_excluded_even_if_pet_is_local(self):
        other_branch = Branch.objects.create(
            name='Other Geo Mapping Branch',
            phone_number='09123456780',
            address='2 Test Street',
            city='Other City',
            state='Test State',
            zip_code='1001',
        )
        pet = Pet.objects.create(
            name='Local Pet With Other-Branch Record',
            species='Dog',
            sex=Pet.Sex.MALE,
            branch=self.branch,
        )
        record = MedicalRecord.objects.create(
            pet=pet,
            branch=other_branch,
            date_recorded=date(2026, 10, 20),
        )
        RecordEntry.objects.create(
            record=record,
            date_recorded=date(2026, 10, 20),
            history_clinical_signs='Persistent cough',
        )

        result = summarize_branch_disease_trends(
            self.branch,
            start_date=date(2026, 10, 1),
            end_date=date(2026, 10, 20),
        )

        self.assertEqual(result['total_cases'], 0)


@override_settings(
    STORAGES={
        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
        'staticfiles': {
            'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage',
        },
    }
)
class DiseaseDashboardViewTests(TestCase):
    def setUp(self):
        self.branch = Branch.objects.create(
            name='Disease Dashboard Test Branch',
            phone_number='09123456789',
            address='1 Test Street',
            city='Test City',
            state='Test State',
            zip_code='1000',
        )
        self.admin = get_user_model().objects.create_superuser(
            username='disease-dashboard-admin',
            email='disease-dashboard-admin@example.com',
            password='A-secure-test-password-923!',
        )
        self.admin.branch = self.branch
        self.admin.save(update_fields=['branch'])
        self.client.force_login(self.admin)

    def test_veterinarian_role_has_disease_mapping_special_permission(self):
        veterinarian = Role.objects.get(code='veterinarian')

        self.assertTrue(
            veterinarian.special_permissions.filter(
                permission__code=SpecialPermissionCodes.DISEASE_GEO_MAPPING,
            ).exists()
        )

    def test_role_editor_exposes_mapping_as_special_permission_not_module(self):
        response = self.client.get(reverse('accounts:role_create'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'special_can_access_disease_geo_mapping')
        self.assertNotContains(response, 'data-module="disease_geo_mapping"')

    def test_superadmin_dashboard_loads_with_default_and_disease_filters(self):
        visit_date = date.today()
        unmatched_pet = Pet.objects.create(
            name='Unmatched Disease Dashboard Pet',
            species='Dog',
            sex=Pet.Sex.MALE,
            branch=self.branch,
        )
        unmatched_record = MedicalRecord.objects.create(
            pet=unmatched_pet,
            branch=self.branch,
            date_recorded=visit_date,
        )
        RecordEntry.objects.create(
            record=unmatched_record,
            date_recorded=visit_date,
            history_clinical_signs='Routine check-up with no specific symptoms',
        )

        for index in range(2):
            pet = Pet.objects.create(
                name=f'Disease Dashboard Pet {index}',
                species='Dog',
                sex=Pet.Sex.MALE,
                branch=self.branch,
            )
            record = MedicalRecord.objects.create(
                pet=pet,
                branch=self.branch,
                date_recorded=visit_date,
            )
            RecordEntry.objects.create(
                record=record,
                date_recorded=visit_date,
                history_clinical_signs='Pneumonia with persistent cough',
            )

        other_branch = Branch.objects.create(
            name='Other Dashboard Branch',
            phone_number='09123456780',
            address='2 Test Street',
            city='Other City',
            state='Test State',
            zip_code='1001',
        )
        other_pet = Pet.objects.create(
            name='Other Dashboard Pet',
            species='Dog',
            sex=Pet.Sex.MALE,
            branch=other_branch,
        )
        other_record = MedicalRecord.objects.create(
            pet=other_pet,
            branch=other_branch,
            date_recorded=visit_date,
        )
        RecordEntry.objects.create(
            record=other_record,
            date_recorded=visit_date,
            history_clinical_signs='Pneumonia with persistent cough',
        )

        url = reverse('disease_geo_mapping:dashboard')

        default_response = self.client.get(url)
        filtered_response = self.client.get(url, {
            'branch': other_branch.pk,
            'disease_type': 'Respiratory',
        })

        self.assertEqual(default_response.status_code, 200)
        self.assertEqual(filtered_response.status_code, 200)
        self.assertEqual(
            filtered_response.context['selected_disease_type'],
            'Respiratory',
        )
        self.assertEqual(
            filtered_response.context['selected_branch_id'],
            str(self.branch.pk),
        )
        self.assertEqual(filtered_response.context['total_cases'], 2)
        self.assertContains(filtered_response, 'Pneumonia')

    def test_veterinarian_special_permission_grants_only_own_branch_mapping(self):
        other_branch = Branch.objects.create(
            name='Vet Other Branch',
            phone_number='09123456780',
            address='2 Test Street',
            city='Other City',
            state='Test State',
            zip_code='1001',
        )
        role = Role.objects.create(
            name='Disease Mapping Veterinarian',
            code='disease-mapping-veterinarian',
            hierarchy_level=3,
            is_staff_role=True,
        )
        permission = SpecialPermission.objects.get(
            code=SpecialPermissionCodes.DISEASE_GEO_MAPPING,
        )
        RoleSpecialPermission.objects.create(role=role, permission=permission)
        vet = get_user_model().objects.create_user(
            username='disease-mapping-vet',
            email='disease-mapping-vet@example.com',
            password='A-secure-test-password-923!',
            branch=self.branch,
            assigned_role=role,
        )
        self.client.force_login(vet)

        response = self.client.get(
            reverse('disease_geo_mapping:dashboard'),
            {'branch': other_branch.pk},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['selected_branch_id'], str(self.branch.pk))
        self.assertTrue(response.context['branch_restricted'])

    def test_old_module_permission_alone_does_not_grant_mapping_access(self):
        module = Module.objects.get(code='disease_geo_mapping')
        role = Role.objects.create(
            name='Legacy Disease Module Role',
            code='legacy-disease-module-role',
            hierarchy_level=3,
            is_staff_role=True,
        )
        ModulePermission.objects.create(
            role=role,
            module=module,
            permission_type=ModulePermission.PermissionType.VIEW,
            restrict_to_branch=True,
        )
        user = get_user_model().objects.create_user(
            username='legacy-disease-module-user',
            email='legacy-disease-module-user@example.com',
            password='A-secure-test-password-923!',
            branch=self.branch,
            assigned_role=role,
        )
        self.client.force_login(user)

        response = self.client.get(reverse('disease_geo_mapping:dashboard'))

        self.assertEqual(response.status_code, 302)
        self.assertNotEqual(response.url, reverse('disease_geo_mapping:dashboard'))