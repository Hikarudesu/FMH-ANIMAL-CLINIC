from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from billing.models import Service
from branches.models import Branch
from inventory.admin import ProductAdmin
from inventory.models import Product
from patients.models import Pet
from records.models import MedicalRecord, RecordEntry


class RecordsArchiveTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser(
            username='archive-superadmin',
            email='archive-superadmin@example.com',
            password='A-secure-test-password-923!',
        )
        self.client.force_login(self.admin)
        self.branch = Branch.objects.create(
            name='Archive Test Branch',
            phone_number='09123456789',
            address='1 Test Street',
            city='Test City',
            state='Test State',
            zip_code='1000',
        )

    def test_records_archive_is_restricted_to_admin_users(self):
        user = get_user_model().objects.create_user(
            username='archive-standard-user',
            email='archive-standard@example.com',
            password='A-secure-test-password-923!',
        )
        self.client.force_login(user)

        response = self.client.get(reverse('accounts:records_archive'))

        self.assertNotEqual(response.status_code, 200)

    def test_records_archive_lists_soft_deleted_record_types(self):
        pet = Pet.objects.create(
            name='Recycle Patient',
            species='Cat',
            sex=Pet.Sex.FEMALE,
        )
        record = MedicalRecord.objects.create(
            pet=pet,
            date_recorded=timezone.localdate(),
        )
        RecordEntry.objects.create(
            record=record,
            date_recorded=timezone.localdate(),
            treatment='Archive treatment',
        )
        product = Product.objects.create(
            name='Archived Medicine',
            branch=self.branch,
            price=25,
        )
        service = Service.objects.create(name='Archived Grooming')
        pet.delete()
        product.delete()
        service.delete()

        response = self.client.get(reverse('accounts:records_archive'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Pet / patient')
        self.assertContains(response, 'Medical record')
        self.assertContains(response, 'Visit history')
        self.assertContains(response, 'Inventory item')
        self.assertContains(response, 'Clinic service')
        self.assertContains(response, 'Recycle Patient')
        self.assertContains(response, 'Archived Medicine')
        self.assertContains(response, 'Archived Grooming')

    def test_archive_restore_recovers_pet_and_its_clinical_history(self):
        pet = Pet.objects.create(
            name='Restorable Patient',
            species='Dog',
            sex=Pet.Sex.MALE,
        )
        record = MedicalRecord.objects.create(
            pet=pet,
            date_recorded=timezone.localdate(),
        )
        entry = RecordEntry.objects.create(
            record=record,
            date_recorded=timezone.localdate(),
        )
        pet.delete()

        response = self.client.post(
            reverse('accounts:restore_archived_record', args=['pet', pet.pk]),
        )

        self.assertEqual(response.status_code, 302)
        pet.refresh_from_db()
        record.refresh_from_db()
        entry.refresh_from_db()
        self.assertFalse(pet.is_deleted)
        self.assertFalse(record.is_deleted)
        self.assertFalse(entry.is_deleted)

    def test_purge_hard_deletes_only_items_past_30_days(self):
        expired_service = Service.objects.create(name='Expired Service')
        recent_service = Service.objects.create(name='Recent Service')
        expired_service.delete()
        recent_service.delete()
        old_timestamp = timezone.now() - timedelta(days=31)
        Service.all_objects.filter(pk=expired_service.pk).update(deleted_at=old_timestamp)

        call_command('purge_expired_archive_items')

        self.assertFalse(Service.all_objects.filter(pk=expired_service.pk).exists())
        self.assertTrue(Service.all_objects.filter(pk=recent_service.pk).exists())

    def test_admin_bulk_delete_uses_soft_delete(self):
        product = Product.objects.create(
            name='Admin Archived Medicine',
            branch=self.branch,
            price=25,
        )

        ProductAdmin(Product, None).delete_queryset(
            self.admin,
            Product.objects.filter(pk=product.pk),
        )

        product.refresh_from_db()
        self.assertTrue(product.is_deleted)
        self.assertTrue(Product.all_objects.filter(pk=product.pk).exists())
