"""Data migration to seed default landing page content."""

from django.db import migrations


def seed_landing_content(apps, schema_editor):
    """Seed default landing page content from hardcoded values."""
    SectionContent = apps.get_model('settings', 'SectionContent')
    HeroStat = apps.get_model('settings', 'HeroStat')
    CoreValue = apps.get_model('settings', 'CoreValue')
    Service = apps.get_model('settings', 'Service')
    Veterinarian = apps.get_model('settings', 'Veterinarian')

    # Seed Hero Section Content
    SectionContent.objects.get_or_create(
        section_type='HERO',
        defaults={
            'title': 'FMH ANIMAL CLINIC',
            'subtitle': 'Powered by AI Diagnostics',
            'description': 'A centralized multi-branch veterinary system offering faster appointments, organized medical records, and AI-assisted diagnostic insights for your beloved pets.',
        }
    )

    # Seed Mission Content
    SectionContent.objects.get_or_create(
        section_type='MISSION',
        defaults={
            'title': 'Our Mission',
            'description': 'We pet care professionals who work as a team to help many people and their pets in our community to have the best human-animal bonding possible by offering optimal health, excellent veterinary care, and stress-free environment.',
        }
    )

    # Seed Vision Content
    SectionContent.objects.get_or_create(
        section_type='VISION',
        defaults={
            'title': 'Our Vision',
            'description': 'Our Vision is to provide the highest level of pet care, through medical innovation, continued education, and advancements in animal healthcare. We will strengthen communication with our clients, and set a precedence of treating them and their pets responsibly, ethically, and individually in family environment, all while inspiring a culture of trust and compassion. Through our community involvement and support, we will promote and nurture the joy of the pet-human bond.',
        }
    )

    # Seed Services Intro
    SectionContent.objects.get_or_create(
        section_type='SERVICES_INTRO',
        defaults={
            'title': 'Our Services',
            'subtitle': 'Comprehensive veterinary care for your beloved pets across all FMH Animal Clinic branches.',
        }
    )

    # Seed Veterinarians Intro
    SectionContent.objects.get_or_create(
        section_type='VETS_INTRO',
        defaults={
            'title': 'Meet Our Veterinarians',
            'subtitle': 'Experienced, compassionate professionals dedicated to your pet\'s health and well-being.',
        }
    )

    # Seed Core Values Intro
    SectionContent.objects.get_or_create(
        section_type='CORE_VALUES_INTRO',
        defaults={
            'title': 'Core Values',
            'subtitle': 'Our core values are:',
        }
    )

    # Seed Hero Stats
    hero_stats = [
        {'value': '3', 'label': 'Clinic Branches', 'order': 1},
        {'value': 'AI', 'label': 'Diagnostic Support', 'order': 2},
        {'value': '24/7', 'label': 'Online Booking', 'order': 3},
    ]
    for stat in hero_stats:
        HeroStat.objects.get_or_create(
            value=stat['value'],
            label=stat['label'],
            defaults={'order': stat['order']}
        )

    # Seed Core Values
    core_values = [
        {'title': 'Compassion', 'icon': 'bx-heart', 'order': 1},
        {'title': 'Integrity', 'icon': 'bx-anchor', 'order': 2},
        {'title': 'Commitment', 'icon': 'bx-pin', 'order': 3},
        {'title': 'Quality of Life', 'icon': 'bx-leaf', 'order': 4},
    ]
    for value in core_values:
        CoreValue.objects.get_or_create(
            title=value['title'],
            defaults={'icon': value['icon'], 'order': value['order']}
        )

    # Seed Services
    services = [
        {'title': 'Consultation & Treatment', 'description': 'Expert veterinary consultations and personalized treatment plans for your pet\'s health and well-being.', 'icon': 'bx-conversation', 'order': 1},
        {'title': 'Animal Wellness Check', 'description': 'Regular wellness examinations to keep your pets healthy with preventive care and early detection.', 'icon': 'bx-heart-circle', 'order': 2},
        {'title': 'Soft Tissue Surgery', 'description': 'Safe and professional surgical procedures performed by experienced veterinary surgeons.', 'icon': 'bx-band-aid', 'order': 3},
        {'title': 'Diagnostics', 'description': 'Advanced diagnostic tools combined with AI-powered analysis for accurate and fast results.', 'icon': 'bx-analyse', 'order': 4},
        {'title': 'Ultrasound / X-Ray', 'description': 'State-of-the-art imaging services for detailed internal examinations and diagnosis.', 'icon': 'bx-pulse', 'order': 5},
        {'title': 'Pet Grooming', 'description': 'Professional grooming services to keep your pets clean, comfortable, and looking their best.', 'icon': 'bx-bath', 'order': 6},
        {'title': 'Emergency Care', 'description': 'Critical care services available for urgent medical situations requiring immediate attention.', 'icon': 'bx-plus-medical', 'order': 7},
        {'title': 'Pet Retail', 'description': 'Premium pet supplies, nutritious food, and essential accessories for your furry friend\'s well-being.', 'icon': 'bx-shopping-bag', 'order': 8},
        {'title': 'Confinement', 'description': 'Secure and comfortable confinement facilities for pets requiring intensive observation or recovery.', 'icon': 'bx-home-heart', 'order': 9},
        {'title': 'Vaccination', 'description': 'Essential vaccinations and tailored immunization plans to protect your pets from harmful diseases.', 'icon': 'bx-injection', 'order': 10},
        {'title': 'Pathology & Laboratory', 'description': 'Comprehensive in-house laboratory testing and pathology services for accurate and timely diagnosis.', 'icon': 'bx-test-tube', 'order': 11},
        {'title': 'Deworming', 'description': 'Safe and effective parasite control to protect your pet\'s health and prevent harmful internal infections.', 'icon': 'bx-shield-plus', 'order': 12},
    ]
    for service in services:
        Service.objects.get_or_create(
            title=service['title'],
            defaults={
                'description': service['description'],
                'icon': service['icon'],
                'order': service['order']
            }
        )

    # Seed Veterinarians
    vets = [
        {
            'name': 'Fortunato Hernandez',
            'title': 'Senior Veterinarian',
            'bio': '30 years of experience in veterinary medicine with specialization in complex surgical procedures and animal healthcare management.',
            'order': 1
        },
        {
            'name': 'Paul Deo Hernandez',
            'title': 'Veterinarian',
            'bio': 'Graduated in Cavite State University-Don Severino Delas Alas Campus. Companion Animal Practitioner for 5 years with expertise in small animal medicine.',
            'order': 2
        },
        {
            'name': 'Lyndon G. Quines',
            'title': 'Veterinarian',
            'bio': 'Graduated Doctor of Veterinary Medicine at Benguet State University La Trinidad, Benguet. Companion Animal Practitioner for 2 years.',
            'order': 3
        },
        {
            'name': 'Shari Rose G. Dao-ines',
            'title': 'Veterinarian',
            'bio': 'Graduated Doctor of Veterinary Medicine at Benguet State University La Trinidad, Benguet. Companion Animal Practitioner for 3 years with focus on preventive care.',
            'order': 4
        },
    ]
    for vet in vets:
        Veterinarian.objects.get_or_create(
            name=vet['name'],
            defaults={
                'title': vet['title'],
                'bio': vet['bio'],
                'order': vet['order']
            }
        )


def reverse_seed(apps, schema_editor):
    """Don't delete data on reverse to prevent accidental data loss."""


class Migration(migrations.Migration):
    """Data migration to seed default landing page content."""

    dependencies = [
        ('settings', '0003_corevalue_herostat_sectioncontent_service_and_more'),
    ]

    operations = [
        migrations.RunPython(seed_landing_content, reverse_seed),
    ]
