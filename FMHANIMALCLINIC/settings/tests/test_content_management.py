from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from settings.models import SectionContent


class MissionVisionPublishingTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser(
            username='content-admin',
            email='content-admin@example.com',
            password='A-secure-test-password-923!',
        )
        self.client.force_login(self.admin)

    def test_saved_mission_and_vision_content_appears_on_homepage(self):
        response = self.client.post(reverse('settings:content_settings'), {
            'form_type': 'content',
            'sub_form': 'mission_vision',
            'mission_title': 'Mission Updated For Test',
            'mission_description': 'Mission description updated for test.',
            'vision_title': 'Vision Updated For Test',
            'vision_description': 'Vision description updated for test.',
            'core_values_title': 'Values Updated For Test',
            'core_values_description': 'Values description updated for test.',
        }, follow=True)

        self.assertContains(response, 'Mission, Vision &amp; Core Values Intro updated successfully.')
        self.assertEqual(
            SectionContent.objects.get(section_type='MISSION').title,
            'Mission Updated For Test',
        )
        self.assertEqual(
            SectionContent.objects.get(section_type='VISION').description,
            'Vision description updated for test.',
        )

        homepage = self.client.get(reverse('landing_page'))
        self.assertContains(homepage, 'Mission Updated For Test')
        self.assertContains(homepage, 'Mission description updated for test.')
        self.assertContains(homepage, 'Vision Updated For Test')
        self.assertContains(homepage, 'Vision description updated for test.')
        self.assertContains(homepage, 'Values Updated For Test')