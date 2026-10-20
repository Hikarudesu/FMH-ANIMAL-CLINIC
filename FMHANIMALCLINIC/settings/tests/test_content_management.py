from io import BytesIO
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from branches.models import Branch
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
class BranchesMapContentManagementTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser(
            username='branches-map-admin',
            email='branches-map-admin@example.com',
            password='A-secure-test-password-923!',
        )
        self.client.force_login(self.admin)

    def test_branches_map_heading_and_tagline_are_editable(self):
        branch = Branch.objects.create(
            name='Map Content Test Branch',
            phone_number='09123456789',
            address='1 Clinic Street',
            city='Manila',
            state='NCR',
            zip_code='1000',
            google_maps_embed_url='https://www.google.com/maps/embed?pb=branch-test',
        )
        response = self.client.post(reverse('settings:content_settings'), {
            'form_type': 'content',
            'sub_form': 'branches_map_intro',
            'title': 'Visit Our Locations',
            'subtitle': 'Across the Region',
            'description': 'Choose a branch to see its location and hours.',
        }, follow=True)

        self.assertContains(response, 'Branches map section updated successfully.')
        self.assertContains(response, 'Branches Map')

        contact_page = self.client.get(reverse('contact_page'))
        self.assertContains(contact_page, 'Visit Our Locations')
        self.assertContains(contact_page, 'Across the Region')
        self.assertContains(
            contact_page,
            'Choose a branch to see its location and hours.',
        )
        self.assertContains(contact_page, branch.name)
        self.assertContains(contact_page, branch.google_maps_embed_url)
        self.assertContains(
            response,
            'Branch cards, addresses, contact details, operating hours, map embeds, and display order are managed in the Branches section.',
        )


@override_settings(STORAGES=TEST_STORAGES)
class QuickAccessContentManagementTests(TestCase):
    def setUp(self):
        self.media_directory = tempfile.TemporaryDirectory()
        self.settings_override = override_settings(MEDIA_ROOT=self.media_directory.name)
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        self.addCleanup(self.media_directory.cleanup)
        self.admin = get_user_model().objects.create_superuser(
            username='quick-access-admin',
            email='quick-access-admin@example.com',
            password='A-secure-test-password-923!',
        )
        self.client.force_login(self.admin)

    def test_section_and_cards_are_editable_and_subject_image_is_autocropped(self):
        intro_response = self.client.post(reverse('settings:content_settings'), {
            'form_type': 'content',
            'sub_form': 'quick_access_intro',
            'title': 'Explore Our',
            'subtitle': 'Updated Clinic',
            'description': 'Find the information you need.',
        }, follow=True)
        self.assertContains(intro_response, 'Quick access section updated successfully.')

        source = Image.new('RGBA', (100, 90), (0, 0, 0, 0))
        source.alpha_composite(Image.new('RGBA', (30, 40), (0, 255, 0, 255)), (20, 15))
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
                'subject_image': SimpleUploadedFile(
                    'transparent-subject.png',
                    image_buffer.getvalue(),
                    content_type='image/png',
                ),
            },
            follow=True,
        )

        self.assertContains(response, 'Quick access card added successfully.')
        card = QuickAccessCard.objects.get(title='New Dynamic Card')
        with Image.open(card.subject_image.path) as cropped_image:
            self.assertEqual(cropped_image.size, (30, 40))
            self.assertEqual(cropped_image.mode, 'RGBA')
            self.assertEqual(cropped_image.getpixel((0, 0)), (0, 255, 0, 255))

        homepage = self.client.get(reverse('landing_page'))
        self.assertContains(homepage, 'Explore Our')
        self.assertContains(homepage, 'Updated Clinic')
        self.assertContains(homepage, 'New Dynamic Card')
        self.assertContains(homepage, 'A dynamically managed homepage card.')
        self.assertContains(homepage, card.subject_image.url)
        self.assertContains(homepage, 'quick-subject-img')
        self.assertContains(response, 'Card background artwork stays fixed')
        self.assertNotContains(response, 'name="fallback_image"')

    def test_quick_access_card_rejects_unsafe_link_and_can_be_deleted(self):
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

        card = QuickAccessCard.objects.get(title='Our Services')
        response = self.client.post(
            reverse('settings:content_settings'),
            {
                'delete_item_form_type': 'delete_quick_access_card',
                'delete_item_id': str(card.pk),
            },
            follow=True,
        )
        self.assertContains(response, 'Quick access card deleted.')
        self.assertFalse(QuickAccessCard.objects.filter(pk=card.pk).exists())


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