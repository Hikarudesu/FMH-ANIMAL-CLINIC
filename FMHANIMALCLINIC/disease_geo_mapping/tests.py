from datetime import date, timedelta

from django.test import SimpleTestCase, TestCase

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

    def test_aggregates_every_matching_visit_and_pet_profile(self):
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
        prediction = result['disease_counts'][0]
        self.assertEqual(prediction['value'], 501)
        self.assertEqual(prediction['distinct_pets'], 2)
        self.assertIn('Dog / Labrador / Male', prediction['pet_profile_summary'])
        self.assertIn('Cat / Siamese / Female', prediction['pet_profile_summary'])

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