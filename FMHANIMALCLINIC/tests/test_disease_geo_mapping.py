from datetime import date, timedelta

from django.test import TestCase

from branches.models import Branch
from disease_geo_mapping.services import summarize_branch_disease_trends
from disease_geo_mapping.views import _get_branch_selection
from diagnostics.models import AIDiagnosis
from patients.models import Pet
from records.models import MedicalRecord, RecordEntry


class DiseaseGeoMappingTests(TestCase):
    def test_empty_branch_returns_warning(self):
        branch = Branch.objects.create(
            name='Test Branch',
            phone_number='12345',
            address='123 Main',
            city='Quezon',
            state='Metro',
            zip_code='1111',
        )

        payload = summarize_branch_disease_trends(branch)

        self.assertTrue(payload['show_warning'])
        self.assertIn('No results', payload['warning'])

    def test_disease_type_filter_returns_matching_counts(self):
        branch = Branch.objects.create(
            name='Filter Branch',
            phone_number='12345',
            address='456 Elm',
            city='Quezon',
            state='Metro',
            zip_code='1111',
        )
        pet = Pet.objects.create(
            name='Rex',
            species='Dog',
            sex='MALE',
            branch=branch,
        )

        AIDiagnosis.objects.create(
            pet=pet,
            primary_condition='Canine Parvovirus',
            primary_reasoning='Suspected due to vomiting and diarrhea',
        )
        AIDiagnosis.objects.create(
            pet=pet,
            primary_condition='Kennel Cough',
            primary_reasoning='Dry cough and sneezing',
        )

        payload = summarize_branch_disease_trends(branch, disease_type='Parvo')

        self.assertFalse(payload['show_warning'])
        self.assertEqual(len(payload['disease_counts']), 1)
        self.assertEqual(payload['disease_counts'][0]['name'], 'Canine Parvovirus')

    def test_date_range_filter_excludes_old_records(self):
        branch = Branch.objects.create(
            name='Date Branch',
            phone_number='12345',
            address='789 Oak',
            city='Quezon',
            state='Metro',
            zip_code='1111',
        )
        pet = Pet.objects.create(
            name='Milo',
            species='Cat',
            sex='MALE',
            branch=branch,
        )

        today = date.today()
        old_date = today - timedelta(days=30)
        recent_date = today - timedelta(days=2)

        old_diag = AIDiagnosis.objects.create(
            pet=pet,
            primary_condition='Feline Influenza',
            primary_reasoning='Recent fever and lethargy',
        )
        recent_diag = AIDiagnosis.objects.create(
            pet=pet,
            primary_condition='Feline Influenza',
            primary_reasoning='Ongoing fever',
        )

        AIDiagnosis.objects.filter(pk=old_diag.pk).update(created_at=old_date)
        AIDiagnosis.objects.filter(pk=recent_diag.pk).update(created_at=recent_date)

        payload = summarize_branch_disease_trends(
            branch,
            start_date=recent_date,
            end_date=today,
        )

        self.assertFalse(payload['show_warning'])
        self.assertEqual(payload['total_cases'], 1)
        self.assertEqual(payload['disease_counts'][0]['value'], 1)

    def test_medical_record_entries_are_counted_for_branch(self):
        branch = Branch.objects.create(
            name='Record Branch',
            phone_number='12345',
            address='111 Pine',
            city='Quezon',
            state='Metro',
            zip_code='1111',
        )
        pet = Pet.objects.create(
            name='Bella',
            species='Dog',
            sex='FEMALE',
            branch=branch,
        )
        record = MedicalRecord.objects.create(
            pet=pet,
            branch=branch,
            date_recorded=date.today(),
            history_clinical_signs='Has coughing and fever',
        )
        RecordEntry.objects.create(
            record=record,
            date_recorded=date.today(),
            history_clinical_signs='Coughing and fever',
            treatment='Antibiotics',
            rx='Amoxicillin',
        )

        payload = summarize_branch_disease_trends(branch)

        self.assertFalse(payload['show_warning'])
        self.assertEqual(payload['total_cases'], 1)
        self.assertEqual(payload['disease_counts'][0]['value'], 1)

    def test_branch_restricted_selection_uses_only_preferred_branch(self):
        branch = Branch.objects.create(
            name='Restricted Branch',
            phone_number='12345',
            address='222 Oak',
            city='Quezon',
            state='Metro',
            zip_code='1111',
        )
        other_branch = Branch.objects.create(
            name='Other Branch',
            phone_number='67890',
            address='333 Pine',
            city='Quezon',
            state='Metro',
            zip_code='1111',
        )

        class DummyUser:
            def __init__(self, branch):
                self.branch = branch
                self.branch_id = branch.id if branch else None

            def is_module_branch_restricted(self, module_name):
                return True

        class DummyRequest:
            def __init__(self, user):
                self.user = user
                self.GET = {}

        request = DummyRequest(DummyUser(branch))
        branches = Branch.objects.filter(pk__in=[branch.pk, other_branch.pk])

        selected_branch = _get_branch_selection(request, branches, True)

        self.assertEqual(selected_branch, branch)
