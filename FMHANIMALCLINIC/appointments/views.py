"""Views for managing appointments, availability, and scheduling."""
from datetime import date, timedelta, datetime, time
import calendar as cal_mod

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_GET
from django.db.models import Q

from accounts.models import User
from accounts.decorators import module_permission_required
from branches.models import Branch
from employees.models import StaffMember, VetSchedule
from notifications.models import FollowUp, Notification
from patients.models import Pet
from .models import Appointment
from .forms import PublicAppointmentForm, PortalAppointmentForm, AdminQuickCreateForm, AppointmentEditForm
from .services import AppointmentService
from notifications.email_utils import send_appointment_confirmation


# ──────────────────────── AVAILABILITY ENGINE ────────────────────────
# Legacy function - delegates to AppointmentService for backward compatibility

def get_available_slots(vet_id=None, target_date=None, branch_id=None, exclude_appointment_id=None):
    """
    Legacy wrapper for AppointmentService.get_available_slots.
    Kept for backward compatibility with existing code.
    """
    return AppointmentService.get_available_slots(
        vet_id=vet_id,
        target_date=target_date,
        branch_id=branch_id,
        exclude_appointment_id=exclude_appointment_id
    )


# ──────────────────────── PUBLIC BOOKING (no login) ────────────────────────

def public_book(request):
    """Public appointment booking — no login required."""
    # Cleanup expired appointments on page load
    Appointment.cleanup_expired()

    if request.method == 'POST':
        form = PublicAppointmentForm(request.POST)
        if form.is_valid():
            appointment = form.save()
            send_appointment_confirmation(appointment)
            messages.success(
                request,
                'Your appointment has been booked successfully! We will contact you to confirm.'
            )
            return redirect('appointments:book_success')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = PublicAppointmentForm()

    branches = Branch.objects.filter(is_active=True)
    return render(request, 'appointments/book_public.html', {
        'form': form,
        'branches': branches,
    })


def book_success(request):
    """Success page after booking."""
    return render(request, 'appointments/book_success.html')


# ──────────────────────── PORTAL BOOKING (logged-in) ────────────────────────

@login_required
def portal_book(request):
    """Logged-in user appointment booking."""
    Appointment.cleanup_expired()

    if request.method == 'POST':
        form = PortalAppointmentForm(request.POST, user=request.user)
        if form.is_valid():
            appointment = form.save()
            send_appointment_confirmation(appointment)
            messages.success(
                request, 'Your appointment has been booked successfully!')
            return redirect('appointments:my_appointments')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = PortalAppointmentForm(user=request.user)

    branches = Branch.objects.filter(is_active=True)
    user_pets = request.user.pets.filter(is_active=True) if hasattr(request.user, 'pets') else []

    return render(request, 'appointments/book_portal.html', {
        'form': form,
        'branches': branches,
        'user_pets': user_pets,
    })


@login_required
def my_appointments(request):
    """Show the logged-in user's appointments and follow-ups with tabbed data."""
    # Base query for appointments - filter out appointments where pet was deleted
    # FIX: Added pet and pet__owner to select_related to prevent N+1 queries
    base_appts = Appointment.objects.filter(
        user=request.user, pet__isnull=False).select_related('branch', 'preferred_vet', 'pet', 'pet__owner')

    # Categorized queries
    pending_appts = base_appts.filter(status=Appointment.Status.PENDING)
    confirmed_appts = base_appts.filter(status=Appointment.Status.CONFIRMED)
    completed_appts = base_appts.filter(status=Appointment.Status.COMPLETED)
    cancelled_appts = base_appts.filter(status=Appointment.Status.CANCELLED)

    # Categorized queries
    follow_ups = FollowUp.objects.filter(
        appointment__user=request.user
    ).select_related('appointment', 'appointment__pet')

    context = {
        'pending_appts': pending_appts,
        'confirmed_appts': confirmed_appts,
        'completed_appts': completed_appts,
        'cancelled_appts': cancelled_appts,
        'follow_ups': follow_ups,
    }
    return render(request, 'appointments/appointments_user.html', context)


# ──────────────────────── AJAX API ENDPOINTS ────────────────────────

@require_GET
def api_available_vets(request):
    """Return available vets and vet assistants for a given branch and date."""
    branch_id = request.GET.get('branch')
    appt_date = request.GET.get('date')

    if not branch_id:
        return JsonResponse({'vets': []})

    # Schedulable roles: veterinarians and vet assistants
    schedulable_roles = ['veterinarian', 'vet_assistant']

    # If a date is provided, only return staff who have a schedule that day
    if appt_date:
        scheduled_staff_ids = VetSchedule.objects.filter(
            branch_id=branch_id,
            date=appt_date,
            is_available=True,
        ).values_list('staff_id', flat=True).distinct()

        # Only return vets/vet assistants who are actually scheduled on this date
        vets = StaffMember.objects.filter(
            id__in=scheduled_staff_ids,
            user__assigned_role__code__in=schedulable_roles,
            is_active=True,
        ).select_related('user', 'user__assigned_role')
    else:
        # No date provided - return all vets/vet assistants assigned to this branch
        vets = StaffMember.objects.filter(
            user__assigned_role__code__in=schedulable_roles,
            is_active=True,
            branch_id=branch_id,
        ).select_related('user', 'user__assigned_role')

    data = [{'id': v.id, 'name': v.full_name} for v in vets]
    
    # Include availability flag for frontend UX
    has_vets = len(data) > 0
    return JsonResponse({
        'vets': data,
        'has_vets': has_vets,
        'availability_message': 'No vets scheduled for this date' if appt_date and not has_vets else None
    })


@require_GET
def api_vet_times(request):
    """Return available time slots for a vet on a given date using the availability engine."""
    vet_id = request.GET.get('vet')
    appt_date = request.GET.get('date')
    branch_id = request.GET.get('branch')
    exclude_appointment_id = request.GET.get('exclude_appointment_id')

    if not appt_date:
        return JsonResponse({'times': []})

    try:
        target_date = date.fromisoformat(appt_date)
    except ValueError:
        return JsonResponse({'times': []})

    # Convert exclude_appointment_id to int if provided
    exclude_appt_id = None
    if exclude_appointment_id:
        try:
            exclude_appt_id = int(exclude_appointment_id)
        except (ValueError, TypeError):
            pass

    # Check if any vets are scheduled on this date
    has_scheduled_vets = VetSchedule.objects.filter(
        date=target_date,
        is_available=True,
        branch_id=int(branch_id) if branch_id else None,
    ).exists() if not vet_id else True  # If specific vet selected, assume they exist
    
    slots = get_available_slots(
        vet_id=int(vet_id) if vet_id else None,
        target_date=target_date,
        branch_id=int(branch_id) if branch_id else None,
        exclude_appointment_id=exclude_appt_id,
    )

    return JsonResponse({
        'times': slots,
        'has_scheduled_vets': has_scheduled_vets,
    })


@require_GET
def api_available_dates(request):
    """Return dates where a specific vet has schedule entries for a given month.
    Used for greying out unavailable dates in the booking calendar."""
    vet_id = request.GET.get('vet')
    year = request.GET.get('year')
    month = request.GET.get('month')
    branch_id = request.GET.get('branch')

    if not (vet_id and year and month):
        return JsonResponse({'dates': []})

    try:
        year = int(year)
        month = int(month)
    except (ValueError, TypeError):
        return JsonResponse({'dates': []})

    _, last_day = cal_mod.monthrange(year, month)

    filters = {
        'staff_id': vet_id,
        'date__gte': date(year, month, 1),
        'date__lte': date(year, month, last_day),
        'is_available': True,
    }
    if branch_id:
        filters['branch_id'] = branch_id

    available_dates = VetSchedule.objects.filter(
        **filters
    ).values_list('date', flat=True).distinct()

    return JsonResponse({
        'dates': [d.isoformat() for d in available_dates],
        'year': year,
        'month': month,
    })


# ──────────────────────── ADMIN — APPOINTMENT MANAGEMENT ────────────────────────

@login_required
@module_permission_required('appointments', 'VIEW')
def admin_list(request):
    """Admin view: list all appointments with filters + calendar support."""
    Appointment.cleanup_expired()

    appointments = Appointment.objects.select_related(
        'branch', 'preferred_vet', 'user').all()

    # Check if user is branch-restricted for appointments
    is_branch_restricted = request.user.is_module_branch_restricted('appointments')
    user_branch = request.user.branch
    
    # If branch restricted, filter appointments to user's branch only
    if is_branch_restricted and user_branch:
        appointments = appointments.filter(branch=user_branch)

    # Search
    q = request.GET.get('q', '').strip()
    if q:
        appointments = appointments.filter(
            Q(owner_name__icontains=q) |
            Q(pet_name__icontains=q) |
            Q(owner_email__icontains=q)
        )

    # Status filter
    status = request.GET.get('status', '')
    if status:
        appointments = appointments.filter(status=status)

    # Branch filter (only apply if user is NOT branch restricted)
    branch_id = request.GET.get('branch', '')
    if branch_id and not is_branch_restricted:
        appointments = appointments.filter(branch_id=branch_id)

    # Source filter
    source = request.GET.get('source', '')
    if source:
        appointments = appointments.filter(source=source)

    # Vet filter
    vet_id = request.GET.get('vet', '')
    if vet_id:
        appointments = appointments.filter(preferred_vet_id=vet_id)

    # View parameter (table, daily, weekly, monthly)
    current_view = request.GET.get('view', 'table')

    # Only show branches if user is NOT branch restricted
    if is_branch_restricted:
        branches = []  # Empty - no branch dropdown
    else:
        branches = Branch.objects.filter(is_active=True)
    
    # Include both veterinarians and vet assistants in the filter dropdown
    vets = StaffMember.objects.filter(
        user__assigned_role__code__in=['veterinarian', 'vet_assistant'],
        is_active=True,
    ).select_related('user', 'user__assigned_role')
    quick_form = AdminQuickCreateForm(initial={'status': 'CONFIRMED'})

    # Pagination (only for table view)
    page_number = request.GET.get('page', 1)
    paginator = Paginator(appointments, 10)
    page_obj = paginator.get_page(page_number)

    # Check permissions for CRUD buttons
    can_create = request.user.has_module_permission('appointments', 'CREATE')
    can_edit = request.user.has_module_permission('appointments', 'EDIT')
    can_delete = request.user.has_module_permission('appointments', 'DELETE')

    return render(request, 'appointments/admin_list.html', {
        'appointments': page_obj,
        'page_obj': page_obj,
        'branches': branches,
        'vets': vets,
        'statuses': Appointment.Status.choices,
        'sources': Appointment.Source.choices,
        'q': q,
        'selected_status': status,
        'selected_branch': branch_id,
        'selected_source': source,
        'selected_vet': vet_id,
        'current_view': current_view,
        'quick_form': quick_form,
        'is_branch_restricted': is_branch_restricted,
        'user_branch': user_branch,
        'can_create': can_create,
        'can_edit': can_edit,
        'can_delete': can_delete,
    })


@login_required
@module_permission_required('appointments', 'VIEW')
def admin_calendar_api(request):
    """JSON API — returns appointments for calendar rendering with filters."""
    try:
        year = int(request.GET.get('year', date.today().year))
    except (ValueError, TypeError):
        year = date.today().year
    try:
        month = int(request.GET.get('month', date.today().month))
    except (ValueError, TypeError):
        month = date.today().month

    _, last_day = cal_mod.monthrange(year, month)
    start = date(year, month, 1)
    end = date(year, month, last_day)

    appointments = Appointment.objects.filter(
        appointment_date__gte=start,
        appointment_date__lte=end,
    ).select_related('branch', 'preferred_vet', 'pet', 'user').exclude(status='CANCELLED')

    # Check if user is branch-restricted for appointments
    is_branch_restricted = request.user.is_module_branch_restricted('appointments')
    user_branch = request.user.branch
    
    # If branch restricted, filter appointments to user's branch only
    if is_branch_restricted and user_branch:
        appointments = appointments.filter(branch=user_branch)

    # Apply filters (branch filter only if NOT restricted)
    branch_id = request.GET.get('branch')
    if branch_id and not is_branch_restricted:
        appointments = appointments.filter(branch_id=branch_id)

    vet_id = request.GET.get('vet')
    if vet_id:
        appointments = appointments.filter(preferred_vet_id=vet_id)

    status = request.GET.get('status')
    if status:
        appointments = appointments.filter(status=status)

    events = []
    for a in appointments:
        # Get pet clinical data if linked
        pet_clinical_status = None
        pet_clinical_display = None
        has_medical_records = False
        latest_record_id = None
        if a.pet:
            pet_clinical_status = a.pet.clinical_status.code if a.pet.clinical_status else None
            pet_clinical_display = a.pet.status_display
            latest_record = a.pet.medical_records.first()
            if latest_record:
                has_medical_records = True
                latest_record_id = latest_record.id

        events.append({
            'id': a.id,
            'petId': a.pet.id if a.pet else None,
            'latestRecordId': latest_record_id,
            'petName': a.pet_name or '',
            'petBreed': a.pet_breed or '',
            'petSpecies': a.pet_species or 'Unknown',
            'petDOB': a.pet.date_of_birth.isoformat() if a.pet and a.pet.date_of_birth else None,
            'petSex': a.pet.sex if a.pet and a.pet.sex else '',
            'petColor': a.pet.color if a.pet and a.pet.color else '',
            'petClinicalStatus': pet_clinical_status,
            'petClinicalDisplay': pet_clinical_display,
            'hasMedicalRecords': has_medical_records,
            'ownerName': a.owner_name or '',
            'ownerEmail': a.owner_email or '',
            'ownerPhone': a.owner_phone or '',
            'ownerProfilePicture': a.user.profile_picture.url if a.user and a.user.profile_picture else None,
            'date': (
                getattr(a, 'appointment_date').isoformat()
                if getattr(a, 'appointment_date', None) else ''
            ),
            'time': (
                getattr(a, 'appointment_time').strftime('%H:%M')
                if getattr(a, 'appointment_time', None) else ''
            ),
            'timeLabel': (
                getattr(a, 'appointment_time').strftime('%I:%M %p')
                if getattr(a, 'appointment_time', None) else ''
            ),
            'branch': a.branch.name if getattr(a, 'branch', None) else '',
            'vetName': a.preferred_vet.full_name if getattr(a, 'preferred_vet', None) else 'Any',
            'vetId': a.preferred_vet.id if getattr(a, 'preferred_vet', None) else 0,
            'status': getattr(a, 'status', ''),
            'statusDisplay': (
                dict(Appointment.Status.choices).get(a.status, a.status)
                if hasattr(Appointment, 'Status') else getattr(a, 'status', '')
            ),
            'source': getattr(a, 'source', ''),
            'reason': (
                a.reason_for_visit.name if a.reason_for_visit else ''
            ),
            'notes': getattr(a, 'notes', ''),
            'createdAt': (
                a.created_at.strftime('%b %d, %Y, %I:%M %p')
                if getattr(a, 'created_at', None) else ''
            )
        })

    return JsonResponse({'events': events, 'year': year, 'month': month})


@login_required
@module_permission_required('appointments', 'CREATE')
def admin_quick_create(request):
    """Admin: quickly create an appointment (walk-in / phone call)."""
    if request.method == 'POST':
        form = AdminQuickCreateForm(request.POST)
        if form.is_valid():
            appointment = form.save()

            # Send email confirmation
            send_appointment_confirmation(appointment)

            # Notify user if appointment is confirmed and has a linked user
            if appointment.status == 'CONFIRMED' and appointment.user:
                Notification.objects.create(
                    user=appointment.user,
                    title=f'Appointment Confirmed for {appointment.pet_name}',
                    message=(
                        f'Great news! Your appointment for {appointment.pet_name} '
                        f'has been confirmed for {appointment.appointment_date.strftime("%B %d, %Y")} '
                        f'at {appointment.appointment_time.strftime("%I:%M %p")}. '
                        f'Location: {appointment.branch.name}.'
                    ),
                    notification_type='APPOINTMENT',
                    module_context=Notification.ModuleContext.APPOINTMENTS,
                )

            # Handle follow-up creation
            follow_up_enabled = request.POST.get('follow_up_enabled')
            if follow_up_enabled == 'on':
                follow_up_date = request.POST.get('follow_up_date')
                follow_up_end_date = request.POST.get('follow_up_end_date')
                follow_up_reason = request.POST.get('follow_up_reason', '')
                if follow_up_date:
                    followup = FollowUp.objects.create(
                        appointment=appointment,
                        pet_name=appointment.pet_name,
                        follow_up_date=follow_up_date,
                        follow_up_end_date=follow_up_end_date if follow_up_end_date else None,
                        reason=follow_up_reason,
                        created_by=request.user,
                    )

                    # Format date string for notification
                    date_str = str(follow_up_date)
                    if follow_up_end_date and follow_up_end_date != follow_up_date:
                        date_str = f"{follow_up_date} to {follow_up_end_date}"

                    # Create notification for the appointment owner
                    if appointment.user:
                        Notification.objects.create(
                            user=appointment.user,
                            title=f'Follow-up Scheduled for {appointment.pet_name}',
                            message=(
                                f'A follow-up visit has been scheduled for {appointment.pet_name} '
                                f'from {date_str}. Reason: {follow_up_reason or "Routine follow-up"}'
                            ),
                            notification_type='FOLLOW_UP',
                            module_context=Notification.ModuleContext.APPOINTMENTS,
                            related_follow_up=followup,
                        )

            messages.success(request, 'Appointment created successfully.')
        else:
            # Include specific form errors in the message for easier debugging
            error_details = ' | '.join([f"{k}: {', '.join(v)}" for k, v in form.errors.items()])
            messages.error(
                request, f'Invalid appointment data. Please check the form. Errors: {error_details}')
    return redirect('appointments:admin_list')


@login_required
@module_permission_required('appointments', 'EDIT')
def admin_edit(request, pk):
    """Admin view: edit an appointment with follow-up support."""
    appointment = get_object_or_404(Appointment, pk=pk)

    if request.method == 'POST':
        # Capture original status before update
        original_status = appointment.status

        form = AppointmentEditForm(request.POST, instance=appointment)
        if form.is_valid():
            updated_appointment = form.save()
            # Sync / update the linked Patient record with any edited pet details
            from appointments.utils import sync_pet_from_appointment
            sync_pet_from_appointment(updated_appointment)

            # Check if status changed and notify user
            if updated_appointment.status != original_status and updated_appointment.user:
                status_notifications = {
                    'CONFIRMED': {
                        'title': f'Appointment Confirmed for {updated_appointment.pet_name}',
                        'message': (
                            f'Great news! Your appointment for {updated_appointment.pet_name} '
                            f'has been confirmed for {updated_appointment.appointment_date.strftime("%B %d, %Y")} '
                            f'at {updated_appointment.appointment_time.strftime("%I:%M %p")}. '
                            f'Location: {updated_appointment.branch.name}.'
                        ),
                    },
                    'COMPLETED': {
                        'title': f'Appointment Completed for {updated_appointment.pet_name}',
                        'message': (
                            f'The appointment for {updated_appointment.pet_name} '
                            f'on {updated_appointment.appointment_date.strftime("%B %d, %Y")} '
                            f'has been marked as completed. Thank you for visiting us!'
                        ),
                    },
                    'CANCELLED': {
                        'title': f'Appointment Cancelled for {updated_appointment.pet_name}',
                        'message': (
                            f'Your appointment for {updated_appointment.pet_name} '
                            f'scheduled on {updated_appointment.appointment_date.strftime("%B %d, %Y")} '
                            f'at {updated_appointment.appointment_time.strftime("%I:%M %p")} '
                            f'has been cancelled. Please contact us if you have any questions.'
                        ),
                    },
                }

                notification_data = status_notifications.get(
                    updated_appointment.status)
                if notification_data:
                    Notification.objects.create(
                        user=updated_appointment.user,
                        title=notification_data['title'],
                        message=notification_data['message'],
                        notification_type='APPOINTMENT',
                        module_context=Notification.ModuleContext.APPOINTMENTS,
                    )

            # Handle follow-up creation
            follow_up_enabled = request.POST.get('follow_up_enabled')
            if follow_up_enabled == 'on':
                follow_up_date = request.POST.get('follow_up_date')
                follow_up_end_date = request.POST.get('follow_up_end_date')
                follow_up_reason = request.POST.get('follow_up_reason', '')
                if follow_up_date:
                    followup = FollowUp.objects.create(
                        appointment=updated_appointment,
                        pet_name=updated_appointment.pet_name,
                        follow_up_date=follow_up_date,
                        follow_up_end_date=follow_up_end_date if follow_up_end_date else None,
                        reason=follow_up_reason,
                        created_by=request.user,
                    )

                    # Format date string for notification
                    date_str = str(follow_up_date)
                    if follow_up_end_date and follow_up_end_date != follow_up_date:
                        date_str = f"{follow_up_date} to {follow_up_end_date}"

                    # Create notification for the appointment owner
                    if updated_appointment.user:
                        Notification.objects.create(
                            user=updated_appointment.user,
                            title=f'Follow-up Scheduled for {updated_appointment.pet_name}',
                            message=(
                                f'A follow-up visit has been scheduled for {updated_appointment.pet_name} '
                                f'from {date_str}. Reason: {follow_up_reason or "Routine follow-up"}'
                            ),
                            notification_type='FOLLOW_UP',
                            module_context=Notification.ModuleContext.APPOINTMENTS,
                            related_follow_up=followup,
                        )
                    messages.info(
                        request, f'Follow-up scheduled from {date_str}.')

            messages.success(
                request, f'Appointment for {updated_appointment.pet_name} updated.')
            return redirect('appointments:admin_list')
    else:
        form = AppointmentEditForm(instance=appointment)

    # Get existing follow-ups for this appointment
    follow_ups = FollowUp.objects.filter(
        appointment=appointment).order_by('-created_at')

    # Get user's pets if appointment has a linked user
    user_pets = []
    if appointment.user:
        user_pets = Pet.objects.filter(owner=appointment.user)

    return render(request, 'appointments/admin_edit.html', {
        'appointment': appointment,
        'form': form,
        'statuses': Appointment.Status.choices,
        'follow_ups': follow_ups,
        'user_pets': user_pets,
    })


@login_required
@module_permission_required('appointments', 'DELETE')
@require_POST
def admin_delete(request, pk):
    """Admin view: delete an appointment."""
    appointment = get_object_or_404(Appointment, pk=pk)
    name = appointment.pet_name
    appointment.delete()
    messages.success(request, f'Appointment for {name} has been deleted.')
    return redirect('appointments:admin_list')


@login_required
@module_permission_required('appointments', 'VIEW')
def api_pet_owners(request):
    """API: return list of registered pet owners for admin dropdown."""
    # Only return users who have at least one pet (pet owners = not staff or no role)
    owners = User.objects.filter(
        pets__isnull=False
    ).filter(
        Q(assigned_role__is_staff_role=False) | Q(assigned_role__isnull=True)
    ).distinct().order_by('first_name', 'last_name', 'username')

    data = []
    for owner in owners:
        full_name = owner.get_full_name() or owner.username
        data.append({
            'id': owner.id,
            'name': full_name,
            'email': owner.email or '',
            'phone': owner.phone_number or '',
            'address': owner.address or '',
        })
    return JsonResponse({'owners': data})


@login_required
@module_permission_required('appointments', 'VIEW')
def api_owner_pets(request):
    """API: return list of pets for a specific owner."""
    from patients.models import Pet
    owner_id = request.GET.get('owner_id')
    if not owner_id:
        return JsonResponse({'pets': []})

    try:
        owner = User.objects.get(pk=owner_id)
    except User.DoesNotExist:
        return JsonResponse({'pets': []})

    pets = Pet.objects.filter(owner=owner, is_active=True).order_by('name')
    data = []
    for pet in pets:
        data.append({
            'id': pet.id,
            'name': pet.name,
            'species': pet.species or '',
            'breed': pet.breed or '',
            'dob': pet.date_of_birth.isoformat() if pet.date_of_birth else '',
            'sex': pet.sex or '',
            'color': pet.color or '',
        })
    return JsonResponse({'pets': data})
