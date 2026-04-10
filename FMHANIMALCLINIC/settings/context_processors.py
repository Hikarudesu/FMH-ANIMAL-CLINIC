"""Context processors for settings."""

import json

from .utils import get_clinic_profile, get_setting


def clinic_settings(request):
    """
    Make commonly-used settings available in all templates.

    Usage in templates:
        {{ CLINIC_NAME }}
        {{ CLINIC_LOGO.url }}
        {{ CURRENCY_SYMBOL }}
        {{ PAYROLL_AUTO_STATUTORY }}
    """
    profile = get_clinic_profile()

    return {
        'CLINIC_NAME': profile.name,
        'CLINIC_LOGO': profile.logo,
        'CLINIC_EMAIL': profile.email,
        'CLINIC_PHONE': profile.phone,
        'CLINIC_ADDRESS': profile.address,
        'CLINIC_TAGLINE': profile.tagline,
        # Hardcoded Philippine Peso (Requirement 2)
        'CURRENCY_SYMBOL': '₱',
        'CURRENCY': 'PHP',
        'MAINTENANCE_MODE': get_setting('system_maintenance_mode', False),
        # Payroll settings
        'PAYROLL_AUTO_STATUTORY': get_setting('payroll_auto_statutory', True),
    }


def landing_content(request):
    """
    Provide landing page content to templates.
    Only loads for non-admin pages to avoid unnecessary queries.

    Usage in templates:
        {{ hero_content.title }}
        {{ mission_content.description }}
        {% for service in services %}...{% endfor %}
        {{ branches_json|safe }}
    """
    # Skip for admin/portal pages to improve performance
    path = request.path
    if path.startswith('/admin/') or path.startswith('/accounts/') or path.startswith('/settings/'):
        return {}

    # Import here to avoid circular imports
    from .models import SectionContent, HeroStat, CoreValue, Service, Veterinarian
    from branches.models import Branch

    # Get section content
    def get_section(section_type):
        try:
            return SectionContent.objects.get(section_type=section_type)
        except SectionContent.DoesNotExist:
            return None

    hero_content = get_section('HERO')
    mission_content = get_section('MISSION')
    vision_content = get_section('VISION')
    services_intro = get_section('SERVICES_INTRO')
    vets_intro = get_section('VETS_INTRO')
    core_values_intro = get_section('CORE_VALUES_INTRO')

    # Get list content
    hero_stats = HeroStat.objects.filter(is_active=True)
    core_values = CoreValue.objects.filter(is_active=True)
    services = Service.objects.filter(is_active=True)
    veterinarians = Veterinarian.objects.filter(is_active=True)

    # Build branches JSON for contact page map
    branches = Branch.objects.filter(is_active=True).order_by('display_order', 'name')
    branches_data = []
    for branch in branches:
        full_address = f"{branch.address}, {branch.city}, {branch.state} {branch.zip_code}"
        branches_data.append({
            'badge': branch.badge_label or branch.name,
            'title': branch.name,
            'address': full_address,
            'phone': branch.phone_number,
            'hours': branch.operating_hours or '',
            'email': branch.email or '',
            'map': branch.google_maps_embed_url or '',
            'link': branch.google_maps_link or '',
            'socials': {
                'fb': branch.facebook_url or '',
                'ig': branch.instagram_url or '',
                'ms': branch.messenger_url or '',
                'tk': branch.tiktok_url or '',
            }
        })

    return {
        'hero_content': hero_content,
        'hero_stats': hero_stats,
        'mission_content': mission_content,
        'vision_content': vision_content,
        'services_intro': services_intro,
        'vets_intro': vets_intro,
        'core_values_intro': core_values_intro,
        'core_values': core_values,
        'services': services,
        'veterinarians': veterinarians,
        'branches': branches,
        'branches_json': json.dumps(branches_data),
    }


def legal_documents(request):
    """
    Provide legal documents (TOS, Privacy Policy) to all templates.

    Usage in templates:
        {{ tos_document.title }}
        {{ tos_document.content|safe }}
        {{ privacy_document.title }}
        {{ privacy_document.content|safe }}
    """
    from .models import LegalDocument

    return {
        'tos_document': LegalDocument.get_tos(),
        'privacy_document': LegalDocument.get_privacy_policy(),
    }

