import re

from django.test import TestCase

from patients.models import Pet


class PetCodeTests(TestCase):
    def test_pet_code_is_generated_and_remains_stable(self):
        pet = Pet.objects.create(
            name='Buddy',
            species='Dog',
            sex=Pet.Sex.MALE,
        )
        original_code = pet.pet_code

        self.assertRegex(original_code, re.compile(r'^[A-Z0-9]{10}$'))

        pet.name = 'Buddy Updated'
        pet.save()

        pet.refresh_from_db()
        self.assertEqual(pet.pet_code, original_code)

    def test_pet_codes_are_unique(self):
        first_pet = Pet.objects.create(
            name='First Pet',
            species='Dog',
            sex=Pet.Sex.MALE,
        )
        second_pet = Pet.objects.create(
            name='Second Pet',
            species='Cat',
            sex=Pet.Sex.FEMALE,
        )

        self.assertNotEqual(first_pet.pet_code, second_pet.pet_code)
