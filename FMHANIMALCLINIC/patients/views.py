"""
Views for managing patient (pet) profiles and displaying their data.
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from django.core.paginator import Paginator

from accounts.decorators import module_permission_required

from records.models import MedicalRecord
from records.views import get_record_missing_fields
from .models import Pet
from .forms import PetForm, AdminPetForm


@login_required
@module_permission_required('patients', 'VIEW')
def admin_list_view(request):
    """Admin view to see all registered patients in the system."""
    # pylint: disable=no-member
    # Fetch choices for filters
    from branches.models import Branch
    from settings.models import ClinicalStatus
    branches = Branch.objects.filter(is_active=True)
    clinical_statuses = ClinicalStatus.objects.filter(is_active=True).order_by('order', 'name')
    
    # Get unique species that actually exist in the DB for the dropdown
    unique_species = Pet.objects.exclude(species__isnull=True).exclude(species='').values_list('species', flat=True).distinct().order_by('species')

    # Check if user is branch-restricted for patients
    is_branch_restricted = request.user.is_module_branch_restricted('patients')
    user_branch = getattr(request.user, 'branch', None)

    query = request.GET.get('q', '')
    status_filter = request.GET.get('status', '')
    branch_filter = request.GET.get('branch', '')
    species_filter = request.GET.get('species', '')
    source_filter = request.GET.get('source', '')

    pets_qs = Pet.objects.select_related('owner', 'owner__branch', 'clinical_status').all().order_by('-id')
    
    # Apply branch restriction first if user is restricted.
    # Walk-In pets have no owner, so owner__branch would silently exclude them.
    # We include Walk-Ins (owner=None) so they are always visible at all branches.
    if is_branch_restricted and user_branch:
        pets_qs = pets_qs.filter(
            Q(owner__branch=user_branch) | Q(owner__isnull=True)
        )

    # Apply Search — covers both portal owners and walk-in guest names
    if query:
        pets_qs = pets_qs.filter(
            Q(name__icontains=query) |
            Q(owner__first_name__icontains=query) |
            Q(owner__last_name__icontains=query) |
            Q(owner__username__icontains=query) |
            Q(guest_owner_name__icontains=query) |
            Q(guest_owner_phone__icontains=query)
        )

    # Apply Filters
    if status_filter:
        try:
            status_id = int(status_filter)
            pets_qs = pets_qs.filter(clinical_status_id=status_id)
        except ValueError:
            pass
    # Branch filter only if not already restricted
    if branch_filter and not is_branch_restricted:
        # Same walk-in fix: include pets with no owner when filtering by branch
        pets_qs = pets_qs.filter(
            Q(owner__branch_id=branch_filter) | Q(owner__isnull=True)
        )
    if species_filter:
        pets_qs = pets_qs.filter(species__iexact=species_filter)
    if source_filter:
        pets_qs = pets_qs.filter(source=source_filter)

    # Pagination
    page_number = request.GET.get('page', 1)
    paginator = Paginator(pets_qs, 10)
    page_obj = paginator.get_page(page_number)
    
    # Get the selected status name for display
    selected_status_name = ''
    if status_filter:
        try:
            selected_status_obj = ClinicalStatus.objects.get(pk=int(status_filter))
            selected_status_name = selected_status_obj.name
        except (ClinicalStatus.DoesNotExist, ValueError):
            pass

    # Check permissions for CRUD buttons
    can_create = request.user.has_module_permission('patients', 'CREATE')
    can_edit = request.user.has_module_permission('patients', 'EDIT')
    can_delete = request.user.has_module_permission('patients', 'DELETE')

    return render(request, 'patients/admin_list.html', {
        'pets': page_obj,
        'page_obj': page_obj,
        'search_query': query,
        'statuses': clinical_statuses,
        'sources': Pet.Source.choices,
        'branches': [] if is_branch_restricted else branches,
        'species_list': unique_species,
        'selected_status': status_filter,
        'selected_status_name': selected_status_name,
        'selected_branch': branch_filter,
        'selected_species': species_filter,
        'selected_source': source_filter,
        'can_create': can_create,
        'can_edit': can_edit,
        'can_delete': can_delete,
        'is_branch_restricted': is_branch_restricted,
    })


@login_required
@module_permission_required('patients', 'VIEW')
def admin_detail_view(request, pk):
    """Admin view showing a full 360° patient profile:
    pet info, owner, medical records, appointments, clinical status."""
    # pylint: disable=no-member
    pet = get_object_or_404(
        Pet.objects.select_related('owner'), pk=pk)

    # All medical records with entries
    medical_records = MedicalRecord.objects.filter(
        pet=pet
    ).select_related('vet', 'branch').prefetch_related('entries').order_by('-date_recorded')

    # All appointments linked to this pet
    from appointments.models import Appointment
    appointments = Appointment.objects.filter(
        pet=pet
    ).select_related('branch', 'preferred_vet').order_by('-appointment_date')[:10]

    # Clinical status history logs
    from patients.models import ClinicalStatusLog
    clinical_logs = ClinicalStatusLog.objects.filter(
        pet=pet
    ).select_related('status').order_by('-created_at')[:20]

    # Latest entry for action_required display
    from records.models import RecordEntry
    latest_entry = RecordEntry.objects.filter(
        record__pet=pet
    ).order_by('-date_recorded', '-created_at').first()

    return render(request, 'patients/admin_detail.html', {
        'pet': pet,
        'owner': pet.owner,  # may be None for walk-in patients
        'medical_records': medical_records,
        'appointments': appointments,
        'clinical_logs': clinical_logs,
        'latest_entry': latest_entry,
    })


@login_required
@module_permission_required('patients', 'VIEW')
def admin_owner_detail_view(request, user_id):
    """Admin view showing owner profile with all their pets, appointments, and notifications."""
    # pylint: disable=no-member
    from django.contrib.auth import get_user_model
    from appointments.models import Appointment
    from notifications.models import Notification
    from accounts.models import UserActivity
    User = get_user_model()

    owner = get_object_or_404(User, pk=user_id)
    pets = Pet.objects.filter(owner=owner)
    appointments = Appointment.objects.filter(
        user=owner
    ).select_related('branch', 'preferred_vet').order_by('-appointment_date')[:15]
    notifications = Notification.objects.filter(
        user=owner
    ).order_by('-created_at')[:50]
    activities = UserActivity.objects.filter(user=owner)[:50]

    return render(request, 'patients/admin_owner_detail.html', {
        'owner': owner,
        'pets': pets,
        'appointments': appointments,
        'notifications': notifications,
        'activities': activities,
    })


@login_required
def my_pets_view(request):
    """Comprehensive My Pets dashboard with pets, appointments, and medical records."""
    # pylint: disable=no-member
    from datetime import date
    from django.db.models import Q
    from appointments.models import Appointment
    from records.models import RecordEntry
    from settings.models import ClinicalStatus

    today = date.today()
    
    # Check if user has any pets at all (independent of filters)
    has_any_pets = Pet.objects.filter(owner=request.user).exists()
    
    # Get filters
    query = request.GET.get('q', '')
    status_filter = request.GET.get('status', '')
    species_filter = request.GET.get('species', '')

    pets_qs = Pet.objects.filter(owner=request.user).prefetch_related(
        'appointments', 'medical_records'
    )

    # Apply Search
    if query:
        pets_qs = pets_qs.filter(
            Q(name__icontains=query) |
            Q(species__icontains=query) |
            Q(breed__icontains=query)
        )

    # Apply Filters
    if status_filter:
        try:
            status_id = int(status_filter)
            pets_qs = pets_qs.filter(clinical_status_id=status_id)
        except ValueError:
            pass
    if species_filter:
        pets_qs = pets_qs.filter(species__iexact=species_filter)

    # Build comprehensive pet data
    active_pets_data = []
    inactive_pets_data = []
    for pet in pets_qs:
        # Get latest clinical entry
        latest_entry = RecordEntry.objects.filter(
            record__pet=pet
        ).select_related('record').order_by('-date_recorded', '-created_at').first()

        # Count appointments and medical records
        total_appointments = Appointment.objects.filter(pet=pet).count()
        upcoming_appointments = Appointment.objects.filter(
            pet=pet,
            appointment_date__gte=today,
        ).exclude(status='CANCELLED').count()
        
        total_records = MedicalRecord.objects.filter(pet=pet).count()
        
        # Calculate age
        age_str = "Unknown"
        if pet.date_of_birth:
            age = today.year - pet.date_of_birth.year
            if today < date(today.year, pet.date_of_birth.month, pet.date_of_birth.day):
                age -= 1
            if age == 0:
                months = (today.year - pet.date_of_birth.year) * 12 + today.month - pet.date_of_birth.month
                age_str = f"{months} month{'s' if months != 1 else ''}"
            else:
                age_str = f"{age} year{'s' if age != 1 else ''}"

        pet_dict = {
            'pet': pet,
            'latest_entry': latest_entry,
            'total_appointments': total_appointments,
            'upcoming_appointments': upcoming_appointments,
            'total_records': total_records,
            'age_str': age_str,
        }
        
        if pet.is_active:
            active_pets_data.append(pet_dict)
        else:
            inactive_pets_data.append(pet_dict)

    # Get upcoming appointments across all pets (check by pet__owner, not just user field)
    upcoming_appointments = Appointment.objects.filter(
        pet__owner=request.user,
        appointment_date__gte=today,
    ).exclude(status='CANCELLED').select_related(
        'pet', 'branch', 'preferred_vet'
    ).order_by('appointment_date', 'appointment_time')[:5]

    # Get recent medical records across all pets
    recent_records = MedicalRecord.objects.filter(
        pet__owner=request.user
    ).select_related('pet', 'vet', 'branch').order_by('-date_recorded')[:5]

    # Pre-compute record warnings for recent records
    record_warnings = {}
    for rec in recent_records:
        entries = rec.entries.all()
        missing = get_record_missing_fields(rec, entries)
        record_warnings[rec.pk] = bool(missing)

    # Get follow-ups
    from notifications.models import FollowUp
    pending_followups = FollowUp.objects.filter(
        appointment__pet__owner=request.user,
        is_completed=False,
        follow_up_date__gte=today,
    ).select_related('appointment__pet').order_by('follow_up_date')[:5]

    # Filters context
    clinical_statuses = ClinicalStatus.objects.filter(is_active=True).order_by('order', 'name')
    unique_species = Pet.objects.filter(owner=request.user).exclude(species__isnull=True).exclude(species='').values_list('species', flat=True).distinct().order_by('species')

    selected_status_name = ''
    if status_filter:
        try:
            selected_status_obj = ClinicalStatus.objects.get(pk=int(status_filter))
            selected_status_name = selected_status_obj.name
        except (ClinicalStatus.DoesNotExist, ValueError):
            pass

    return render(
        request,
        'patients/my_pets.html',
        {
            'active_pets_data': active_pets_data,
            'inactive_pets_data': inactive_pets_data,
            'upcoming_appointments': upcoming_appointments,
            'recent_records': recent_records,
            'record_warnings': record_warnings,
            'pending_followups': pending_followups,
            'search_query': query,
            'statuses': clinical_statuses,
            'species_list': unique_species,
            'selected_status': status_filter,
            'selected_status_name': selected_status_name,
            'selected_species': species_filter,
            'has_any_pets': has_any_pets,
        }
    )


@login_required
def user_pet_detail_view(request, pk):
    """User portal: detailed view of a single pet with medical records, appointments, and clinical status."""
    # pylint: disable=no-member
    pet = get_object_or_404(Pet, pk=pk, owner=request.user)

    # Medical records with entries
    medical_records = MedicalRecord.objects.filter(
        pet=pet
    ).select_related('vet', 'branch').prefetch_related('entries').order_by('-date_recorded')

    # Pre-compute warnings
    record_warnings = {}
    for rec in medical_records:
        entries = rec.entries.all()
        missing = get_record_missing_fields(rec, entries)
        record_warnings[rec.pk] = bool(missing)

    # All appointments linked to this pet
    from appointments.models import Appointment
    appointments = Appointment.objects.filter(
        pet=pet
    ).select_related('branch', 'preferred_vet').order_by('-appointment_date')

    # Latest entry for clinical action display
    from records.models import RecordEntry
    latest_entry = RecordEntry.objects.filter(
        record__pet=pet
    ).order_by('-date_recorded', '-created_at').first()

    return render(request, 'patients/pet_detail.html', {
        'pet': pet,
        'medical_records': medical_records,
        'record_warnings': record_warnings,
        'appointments': appointments,
        'latest_entry': latest_entry,
    })


@login_required
def add_pet_view(request):
    """Add a new pet for the logged-in user."""
    if request.method == 'POST':
        form = PetForm(request.POST, request.FILES)
        if form.is_valid():
            pet = form.save(commit=False)
            pet.owner = request.user
            pet.save()
            messages.success(request, f'{pet.name} has been registered!')
            return redirect('patients:my_pets')
    else:
        form = PetForm()
    return render(request, 'patients/pet_form.html', {'form': form, 'action': 'Register'})



@login_required
def edit_pet_view(request, pk):
    """Edit an existing pet (user portal)."""
    pet = get_object_or_404(Pet, pk=pk, owner=request.user)

    if request.method == 'POST':
        form = PetForm(request.POST, request.FILES, instance=pet)
        if form.is_valid():
            form.save()
            messages.success(request, f'{pet.name} has been updated!')
            return redirect('patients:my_pets')
    else:
        form = PetForm(instance=pet)
    return render(request, 'patients/pet_form.html', {'form': form, 'action': 'Update', 'pet': pet})



@login_required
def delete_pet_view(request, pk):
    """Delete a pet (user portal)."""
    pet = get_object_or_404(Pet, pk=pk, owner=request.user)

    if request.method == 'POST':
        name = pet.name
        pet.delete()
        messages.success(request, f'{name} has been removed.')
        return redirect('patients:my_pets')
    return render(request, 'patients/pet_confirm_delete.html', {'pet': pet})


@login_required
@module_permission_required('patients', 'CREATE')
def admin_add_pet_view(request):
    """Admin view to register a new patient (pet) with owner selection."""
    if request.method == 'POST':
        form = AdminPetForm(request.POST, request.FILES)
        if form.is_valid():
            pet = form.save()
            owner_name = pet.owner.get_full_name() or pet.owner.username if pet.owner else pet.guest_owner_name or 'Walk-in'
            messages.success(request, f'{pet.name} has been registered under {owner_name}!')
            return redirect('patients:admin_detail', pk=pet.pk)
    else:
        form = AdminPetForm()
    return render(request, 'patients/admin_pet_form.html', {'form': form, 'action': 'Register'})


@login_required
@module_permission_required('patients', 'EDIT')
def admin_edit_pet_view(request, pk):
    """Admin view to edit an existing patient (pet)."""
    pet = get_object_or_404(Pet, pk=pk)

    if request.method == 'POST':
        form = AdminPetForm(request.POST, request.FILES, instance=pet)
        if form.is_valid():
            form.save()
            messages.success(request, f'{pet.name} has been updated!')
            return redirect('patients:admin_detail', pk=pet.pk)
    else:
        form = AdminPetForm(instance=pet)
    return render(request, 'patients/admin_pet_form.html', {'form': form, 'action': 'Update', 'pet': pet})


@login_required
@module_permission_required('patients', 'DELETE')
def admin_delete_pet_view(request, pk):
    """Delete a pet from the Admin portal."""
    pet = get_object_or_404(Pet, pk=pk)

    if request.method == 'POST':
        name = pet.name
        pet.delete()
        messages.success(request, f'{name} has been removed.')
        return redirect('patients:admin_list')
    return render(request, 'patients/admin_pet_confirm_delete.html', {'pet': pet})


@login_required
@module_permission_required('patients', 'VIEW')
def delete_notification_view(request, user_id, notification_id):
    """Delete a single notification for a user (admin view)."""
    # pylint: disable=no-member
    from django.http import JsonResponse
    from notifications.models import Notification
    from django.contrib.auth import get_user_model
    User = get_user_model()

    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid method'}, status=405)

    owner = get_object_or_404(User, pk=user_id)
    notification = get_object_or_404(Notification, pk=notification_id, user=owner)
    notification.delete()

    return JsonResponse({'success': True})


@login_required
@module_permission_required('patients', 'VIEW')
def clear_all_notifications_view(request, user_id):
    """Clear all notifications for a user (admin view)."""
    # pylint: disable=no-member
    from django.http import JsonResponse
    from notifications.models import Notification
    from django.contrib.auth import get_user_model
    User = get_user_model()

    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid method'}, status=405)

    owner = get_object_or_404(User, pk=user_id)
    count = Notification.objects.filter(user=owner).count()
    Notification.objects.filter(user=owner).delete()

    return JsonResponse({'success': True, 'count': count})


@login_required
@module_permission_required('patients', 'VIEW')
def delete_activity_view(request, user_id, activity_id):
    """Delete a single activity for a user (admin view)."""
    # pylint: disable=no-member
    from django.http import JsonResponse
    from accounts.models import UserActivity
    from django.contrib.auth import get_user_model
    User = get_user_model()

    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid method'}, status=405)

    owner = get_object_or_404(User, pk=user_id)
    activity = get_object_or_404(UserActivity, pk=activity_id, user=owner)
    activity.delete()

    return JsonResponse({'success': True})


@login_required
@module_permission_required('patients', 'VIEW')
def clear_all_activities_view(request, user_id):
    """Clear all activities for a user (admin view)."""
    # pylint: disable=no-member
    from django.http import JsonResponse
    from accounts.models import UserActivity
    from django.contrib.auth import get_user_model
    User = get_user_model()

    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid method'}, status=405)

    owner = get_object_or_404(User, pk=user_id)
    count = UserActivity.objects.filter(user=owner).count()
    UserActivity.objects.filter(user=owner).delete()

    return JsonResponse({'success': True, 'count': count})
