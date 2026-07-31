"""
Context processors for the patients app.
This module provides the patient_stats context processor,
making patient counts globally available to all templates.
"""
from django.apps import apps


def patient_stats(request):
    """
    Context processor to make patient statistics available to all templates.
    """
    # Exclude unauthorized users from generating heavy queries if needed
    if not request.user.is_authenticated:
        return {}

    # Use apps.get_model to avoid circular loading and pylint 'Import outside toplevel' warnings
    pet_model = apps.get_model('patients', 'Pet')
    appointment_model = apps.get_model('appointments', 'Appointment')

    total_patients_count = pet_model.objects.count()

    context = {
        'total_patients_count': total_patients_count,
    }

    # Fetch dynamic data logic mapped to the specific logged in user:
    # 1. Fetch user's Pets
    user_pets = pet_model.objects.filter(owner=request.user)
    context['sidebar_user_pets'] = user_pets

    # 2. Fetch user's Upcoming Appointment (today or later)
    # Exclude cancelled/completed to get a truly 'upcoming' relevant appointment
    from django.utils import timezone
    now = timezone.now()
    upcoming_appointment = appointment_model.objects.filter(
        user=request.user,
        appointment_date__gte=now.date(),
        status__in=['PENDING', 'CONFIRMED']
    ).order_by('appointment_date', 'appointment_time').first()

    context['sidebar_upcoming_appointment'] = upcoming_appointment

    # Check for user specific role mapping if user is a standard Pet Owner
    if request.user.is_pet_owner():
        user_pets_count = pet_model.objects.filter(owner=request.user).count()
        context['user_pets_count'] = user_pets_count

    return context
