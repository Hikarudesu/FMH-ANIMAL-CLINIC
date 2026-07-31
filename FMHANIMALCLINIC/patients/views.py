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

    # Patients are centralized across the clinic. Everyone with access sees all patients.
    is_branch_restricted = False
    user_branch = getattr(request.user, 'branch', None)

    query = request.GET.get('q', '')
    status_filter = request.GET.get('status', '')
    branch_filter = request.GET.get('branch', '')
    species_filter = request.GET.get('species', '')
    source_filter = request.GET.get('source', '')

    pets_qs = Pet.objects.select_related('owner', 'owner__branch', 'clinical_status').all().order_by('-id')

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
        from records.models import MedicalRecord
        from appointments.models import Appointment
        
        pets_with_appt = Appointment.objects.filter(
            branch_id=branch_filter, pet__isnull=False
        ).values_list('pet_id', flat=True)
        
        pets_with_record = MedicalRecord.objects.filter(
            branch_id=branch_filter
        ).values_list('pet_id', flat=True)
        
        pets_qs = pets_qs.filter(
            Q(branch_id=branch_filter) |
            Q(owner__branch_id=branch_filter) |
            Q(pk__in=pets_with_appt) |
            Q(pk__in=pets_with_record)
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

    can_create_medical_record = request.user.has_module_permission('medical_records', 'CREATE')
    can_view_appointments = request.user.has_module_permission('appointments', 'VIEW')
    can_create_appointments = request.user.has_module_permission('appointments', 'CREATE')

    # Check for credentials from a walk-in → portal conversion
    created_credentials = request.session.pop('created_credentials', None)

    return render(request, 'patients/admin_detail.html', {
        'pet': pet,
        'owner': pet.owner,  # may be None for walk-in patients
        'medical_records': medical_records,
        'appointments': appointments,
        'clinical_logs': clinical_logs,
        'latest_entry': latest_entry,
        'can_create_medical_record': can_create_medical_record,
        'can_view_appointments': can_view_appointments,
        'can_create_appointments': can_create_appointments,
        'created_credentials': created_credentials,
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
            if request.user.branch:
                pet.branch = request.user.branch
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
    """Delete a pet (user portal) — permanently removes the record and all linked data."""
    pet = get_object_or_404(Pet, pk=pk, owner=request.user)

    if request.method == 'POST':
        from appointments.models import Appointment
        name = pet.name
        # Explicitly delete linked appointments first (Appointment.pet uses SET_NULL,
        # so they would otherwise survive as orphaned rows in the database).
        Appointment.objects.filter(pet=pet).delete()
        pet.delete()  # MedicalRecord cascades automatically via on_delete=CASCADE
        messages.success(request, f'{name} has been permanently removed.')
        return redirect('patients:my_pets')
    return render(request, 'patients/pet_confirm_delete.html', {'pet': pet})


@login_required
@module_permission_required('patients', 'CREATE')
def admin_add_pet_view(request):
    """Admin view to register a new patient (pet) with owner selection."""
    if request.method == 'POST':
        form = AdminPetForm(request.POST, request.FILES, user=request.user)
        if form.is_valid():
            pet = form.save()
            owner_name = pet.owner.get_full_name() or pet.owner.username if pet.owner else pet.guest_owner_name or 'Walk-in'
            messages.success(request, f'{pet.name} has been registered under {owner_name}!')
            return redirect('patients:admin_detail', pk=pet.pk)
    else:
        form = AdminPetForm(user=request.user)
    return render(request, 'patients/admin_pet_form.html', {'form': form, 'action': 'Register'})


def _generate_unique_username(full_name):
    """Generate a unique username from a guest owner's full name.
    
    Examples:
        'Juan Dela Cruz' → 'juan.delacruz'
        If taken → 'juan.delacruz2', 'juan.delacruz3', ...
    """
    import re
    from django.contrib.auth import get_user_model
    User = get_user_model()

    # Clean the name
    parts = full_name.strip().split()
    if len(parts) >= 2:
        base = f"{parts[0]}.{''.join(parts[1:])}".lower()
    elif parts:
        base = parts[0].lower()
    else:
        base = 'user'
    # Remove non-alphanumeric (except dots)
    base = re.sub(r'[^a-z0-9.]', '', base)
    if not base:
        base = 'user'

    # Ensure uniqueness
    username = base
    counter = 2
    while User.objects.filter(username=username).exists():
        username = f"{base}{counter}"
        counter += 1
    return username


def _generate_temp_password(length=10):
    """Generate a readable temporary password (letters + digits)."""
    import secrets
    import string
    chars = string.ascii_letters + string.digits
    return ''.join(secrets.choice(chars) for _ in range(length))


def _transfer_walkin_to_user(pet, new_owner):
    """Transfer a walk-in pet and all linked data to a portal user account.
    
    Transfers:
    - Pet.owner, source, guest fields
    - Appointment.user, source, owner_* fields
    - POS Sale.customer, customer_type, guest_* fields
    - Notification user for appointment-related notifications
    """
    from appointments.models import Appointment
    from pos.models import Sale

    # ── 1. Update pet ──
    pet.owner = new_owner
    pet.branch = getattr(new_owner, 'branch', None)
    pet.source = Pet.Source.PORTAL
    pet.guest_owner_name = ''
    pet.guest_owner_phone = ''
    pet.guest_owner_email = ''
    pet.guest_owner_address = ''
    pet.save()

    # ── 2. Re-link all appointments for this pet ──
    pet_appointments = Appointment.objects.filter(pet=pet)
    pet_appointments.update(
        user=new_owner,
        source=Appointment.Source.PORTAL,
        owner_name=new_owner.get_full_name() or new_owner.username,
        owner_phone=new_owner.phone_number or '',
        owner_email=new_owner.email or '',
        owner_address=new_owner.address or '',
    )

    # ── 3. Re-link POS sales linked to this pet ──
    pet_sales = Sale.objects.filter(pet=pet)
    pet_sales.update(
        customer=new_owner,
        customer_type=Sale.CustomerType.REGISTERED,
        guest_name='',
        guest_phone='',
        guest_email='',
        guest_pet_name='',
    )

    # ── 4. Transfer appointment-related notifications ──
    # Notifications are linked to appointment IDs via related_object_id.
    # Re-assign any appointment notifications to the new owner so they
    # appear in the portal user's notification panel.
    from notifications.models import Notification
    appt_ids = list(pet_appointments.values_list('id', flat=True))
    if appt_ids:
        Notification.objects.filter(
            related_object_id__in=appt_ids,
            notification_type__in=[
                Notification.NotificationType.APPOINTMENT,
                Notification.NotificationType.APPOINTMENT_CONFIRMED,
                Notification.NotificationType.APPOINTMENT_CANCELLED,
                Notification.NotificationType.APPOINTMENT_RESCHEDULED,
                Notification.NotificationType.APPOINTMENT_REMINDER_1,
                Notification.NotificationType.APPOINTMENT_REMINDER_2,
                Notification.NotificationType.FOLLOW_UP,
                Notification.NotificationType.FOLLOW_UP_OVERDUE,
            ]
        ).update(user=new_owner)


@login_required
@module_permission_required('patients', 'EDIT')
def admin_edit_pet_view(request, pk):
    """Admin view to edit an existing patient (pet).
    
    Supports two walk-in → portal conversion modes:
    1. **Link Existing** – ``link_to_account`` selects an existing portal user.
    2. **Create New Account** – ``create_new_account`` flag auto-generates a user
       from the guest owner info, displays temporary credentials in a modal.

    In both cases all related data (medical records via Pet FK, appointments)
    are transferred automatically.
    """
    pet = get_object_or_404(Pet, pk=pk)

    # Check if we need to show credentials from a previous create action
    created_credentials = request.session.pop('created_credentials', None)

    if request.method == 'POST':
        form = AdminPetForm(request.POST, request.FILES, instance=pet, user=request.user)
        if form.is_valid():
            link_user = form.cleaned_data.get('link_to_account')
            create_new = form.cleaned_data.get('create_new_account')

            # Server-side guard: only receptionists/superusers can transfer
            user_role = getattr(request.user, 'assigned_role', None)
            is_receptionist = request.user.is_superuser or (user_role and user_role.code == 'receptionist')

            if pet.source == Pet.Source.WALKIN and (create_new or link_user) and is_receptionist:
                if create_new:
                    # ── Mode 2: Create New Account ────────────────────
                    # create_new takes priority — ignore link_user dropdown
                    from django.contrib.auth import get_user_model
                    User = get_user_model()

                    guest_name = pet.guest_owner_name or 'Guest User'
                    name_parts = guest_name.strip().split(maxsplit=1)
                    first_name = name_parts[0] if name_parts else 'Guest'
                    last_name = name_parts[1] if len(name_parts) > 1 else ''

                    username = _generate_unique_username(guest_name)
                    temp_password = _generate_temp_password()

                    new_user = User.objects.create_user(
                        username=username,
                        password=temp_password,
                        first_name=first_name,
                        last_name=last_name,
                        email=pet.guest_owner_email or '',
                        phone_number=pet.guest_owner_phone or '',
                        address=pet.guest_owner_address or '',
                    )

                    # Assign the receptionist's branch to the new portal user
                    # so the pet remains visible in branch-restricted lists
                    receptionist_branch = getattr(request.user, 'branch', None)
                    if receptionist_branch:
                        new_user.branch = receptionist_branch
                        new_user.save(update_fields=['branch'])

                    # Save form changes first, then transfer
                    form.save(commit=False)
                    _transfer_walkin_to_user(pet, new_user)

                    # Store credentials in session for the success modal
                    request.session['created_credentials'] = {
                        'username': username,
                        'password': temp_password,
                        'full_name': new_user.get_full_name() or username,
                        'pet_name': pet.name,
                    }

                    messages.success(
                        request,
                        f'{pet.name} has been linked to a new portal account for '
                        f'{new_user.get_full_name() or username}. '
                        f'Please share the login credentials with the client.'
                    )
                elif link_user:
                    # ── Mode 1: Link to Existing Account ──────────────
                    # If the linked user has no branch, assign receptionist's branch
                    if not link_user.branch:
                        receptionist_branch = getattr(request.user, 'branch', None)
                        if receptionist_branch:
                            link_user.branch = receptionist_branch
                            link_user.save(update_fields=['branch'])

                    form.save(commit=False)
                    _transfer_walkin_to_user(pet, link_user)

                    owner_display = link_user.get_full_name() or link_user.username
                    messages.success(
                        request,
                        f'{pet.name} has been linked to {owner_display}\'s portal account. '
                        f'All medical records and appointments have been transferred.'
                    )
            else:
                form.save()
                messages.success(request, f'{pet.name} has been updated!')

            return redirect('patients:admin_detail', pk=pet.pk)
    else:
        form = AdminPetForm(instance=pet, user=request.user)

    # Expose the can_transfer flag to the template
    can_transfer = getattr(form, '_can_transfer', False)

    return render(request, 'patients/admin_pet_form.html', {
        'form': form,
        'action': 'Update',
        'pet': pet,
        'created_credentials': created_credentials,
        'can_transfer': can_transfer,
    })


@login_required
@module_permission_required('patients', 'DELETE')
def admin_delete_pet_view(request, pk):
    """Delete a pet from the Admin portal — permanently removes the record and all linked data."""
    pet = get_object_or_404(Pet, pk=pk)

    if request.method == 'POST':
        from appointments.models import Appointment
        name = pet.name
        # Explicitly delete linked appointments first (Appointment.pet uses SET_NULL,
        # so they would otherwise survive as orphaned rows in the database).
        Appointment.objects.filter(pet=pet).delete()
        pet.delete()  # MedicalRecord cascades automatically via on_delete=CASCADE
        messages.success(request, f'{name} has been permanently deleted from the system.')
        return redirect('patients:admin_list')
    return redirect('patients:admin_list')


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
