from io import BytesIO
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image, ImageDraw

from settings.models import QuickAccessCard, SectionContent

TEST_STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {
        'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage',
    },
}

@override_settings(STORAGES=TEST_STORAGES)
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


@override_settings(STORAGES=TEST_STORAGES)
class QuickAccessContentManagementTests(TestCase):
    def setUp(self):
        self.media_directory = tempfile.TemporaryDirectory()
        self.settings_override = override_settings(MEDIA_ROOT=self.media_directory.name)
        self.settings_override.enable()
        self.admin = get_user_model().objects.create_superuser(
            username='quick-access-admin',
            email='quick-access-admin@example.com',
            password='A-secure-test-password-923!',
        )
        self.client.force_login(self.admin)

    def tearDown(self):
        self.settings_override.disable()
        self.media_directory.cleanup()
        super().tearDown()

    def test_quick_access_intro_and_uploaded_card_publish_with_autocropped_image(self):
        intro_response = self.client.post(reverse('settings:content_settings'), {
            'form_type': 'content',
            'sub_form': 'quick_access_intro',
            'title': 'Explore Our',
            'subtitle': 'Updated Clinic',
            'description': 'Find the clinic services and information you need.',
        }, follow=True)

        self.assertContains(intro_response, 'Quick access section updated successfully.')
        self.assertContains(intro_response, 'Explore Our')
        self.assertContains(intro_response, 'Updated Clinic')

        source = Image.new('RGB', (2400, 800), 'white')
        draw = ImageDraw.Draw(source)
        draw.rectangle((0, 0, 599, 799), fill='red')
        draw.rectangle((600, 0, 1799, 799), fill=(0, 255, 0))
        draw.rectangle((1800, 0, 2399, 799), fill='blue')
        image_buffer = BytesIO()
        source.save(image_buffer, format='PNG')

        response = self.client.post(
            reverse('settings:content_settings'),
            {
                'form_type': 'content',
                'sub_form': 'quick_access_card',
                'title': 'New Dynamic Card',
                'description': 'A dynamically managed homepage card.',
                'link': '/services/',
                'order': '7',
                'is_active': 'on',
                'image': SimpleUploadedFile(
                    'wide-card.png',
                    image_buffer.getvalue(),
                    content_type='image/png',
                ),
            },
            follow=True,
        )

        self.assertContains(response, 'Quick access card added successfully.')
        card = QuickAccessCard.objects.get(title='New Dynamic Card')
        with Image.open(card.image.path) as cropped_image:
            self.assertEqual(cropped_image.size, (1200, 800))
            center_pixel = cropped_image.getpixel((600, 400))
            self.assertGreater(center_pixel[1], 180)
            self.assertLess(center_pixel[0], 80)
            self.assertLess(center_pixel[2], 80)

        homepage = self.client.get(reverse('landing_page'))
        self.assertContains(homepage, 'New Dynamic Card')
        self.assertContains(homepage, 'A dynamically managed homepage card.')
        self.assertContains(homepage, card.image.url)

    def test_quick_access_card_can_be_edited_deactivated_and_deleted(self):
        card = QuickAccessCard.objects.get(title='Our Services')
        edit_response = self.client.post(
            reverse('settings:content_settings'),
            {
                'form_type': 'content',
                'sub_form': 'quick_access_card',
                'item_id': str(card.pk),
                'title': 'Updated Services Card',
                'description': 'Updated description.',
                'link': '/contact/',
                'order': '9',
            },
            follow=True,
        )

        self.assertContains(edit_response, 'Quick access card updated successfully.')
        card.refresh_from_db()
        self.assertEqual(card.title, 'Updated Services Card')
        self.assertEqual(card.order, 9)
        self.assertFalse(card.is_active)
        self.assertNotContains(self.client.get(reverse('landing_page')), 'Updated Services Card')

        delete_response = self.client.post(
            reverse('settings:content_settings'),
            {
                'delete_item_form_type': 'delete_quick_access_card',
                'delete_item_id': str(card.pk),
            },
            follow=True,
        )
        self.assertContains(delete_response, 'Quick access card deleted.')
        self.assertFalse(QuickAccessCard.objects.filter(pk=card.pk).exists())

    def test_quick_access_card_rejects_unsafe_link_schemes(self):
        self.client.post(reverse('settings:content_settings'), {
            'form_type': 'content',
            'sub_form': 'quick_access_card',
            'title': 'Unsafe Link Card',
            'description': 'Should not be created.',
            'link': 'javascript:alert(1)',
            'order': '1',
            'is_active': 'on',
        })

        self.assertFalse(QuickAccessCard.objects.filter(title='Unsafe Link Card').exists())


@override_settings(STORAGES=TEST_STORAGES)
class RemovedNotificationSettingsTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser(
            username='notification-settings-admin',
            email='notification-settings-admin@example.com',
            password='A-secure-test-password-923!',
        )
        self.client.force_login(self.admin)

    def test_notification_email_controls_are_absent_from_superadmin_settings(self):
        response = self.client.get(reverse('settings:admin_settings'))

        self.assertEqual(response.status_code, 200)
        tab_ids = {tab['id'] for tab in response.context['tabs']}
        self.assertNotIn('notifications', tab_ids)
        self.assertNotContains(response, 'Enable Email Notifications')
        self.assertNotContains(response, 'From Email Address')
        self.assertNotContains(response, 'Sender Display Name')