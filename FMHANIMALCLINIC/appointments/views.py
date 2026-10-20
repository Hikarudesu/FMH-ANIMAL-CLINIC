"""Views for managing appointments, availability, and scheduling."""
from datetime import date, timedelta, datetime, time
import calendar as cal_mod

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_GET
from django.db.models import Q
from django.utils import timezone

from accounts.models import User
from accounts.decorators import module_permission_required
from accounts.rbac_constants import StaffRoles
from branches.models import Branch
from employees.models import StaffMember, VetSchedule
from notifications.models import FollowUp, Notification
from patients.models import Pet
from .models import Appointment, AppointmentHistory
from .forms import (
    PublicAppointmentForm, PortalAppointmentForm, AdminQuickCreateForm,
    AppointmentEditForm, AppointmentCancellationForm,
)
from .clinic_hours import CLINIC_CLOSE_TIME, CLINIC_OPEN_TIME
from .services import AppointmentService
from notifications.email_utils import send_appointment_confirmation
from notifications.utils import (
    create_notification,
    notify_appointment_status_change,
    notify_follow_up_scheduled,
    notify_staff_appointment_status_change,
    notify_veterinarian_consultation_started,
    notify_veterinarian_medical_record_required,
    sync_appointment_follow_up_to_medical_record,
)


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
def _scope_view_only_appointments(user, appointments, *, include_unassigned=False):
    """Limit pure VIEW roles to appointments assigned to their own staff profile."""
    has_management_permission = any(
        user.has_module_permission('appointments', permission)
        for permission in ('CREATE', 'EDIT', 'DELETE')
    )
    if has_management_permission:
        return appointments

    staff = StaffMember.objects.filter(user=user).first()
    if staff is None:
        return appointments.none()
    if include_unassigned:
        return appointments.filter(
            Q(preferred_vet=staff) | Q(preferred_vet__isnull=True)
        )
    return appointments.filter(preferred_vet=staff)



def public_book(request):
    """Public appointment booking — no login required."""
    # Cleanup expired appointments on page load
    Appointment.cleanup_expired()

    if request.method == 'POST':
        with transaction.atomic():
            AppointmentService.lock_booking_schedule(
                request.POST.get('branch'),
                request.POST.get('appointment_date'),
            )
            form = PublicAppointmentForm(request.POST)
            appointment = form.save() if form.is_valid() else None
        if appointment:
            send_appointment_confirmation(appointment)
            notify_staff_appointment_status_change(
                appointment, appointment.status
            )
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


def _add_follow_up_booking_note(appointment, followup):
    """Label the new appointment and preserve any booking notes."""
    note = (
        f'Follow-up visit for the recommendation dated '
        f'{followup.follow_up_date:%B %d, %Y}.'
    )
    if followup.reason:
        note = f'{note} Reason: {followup.reason}'
    existing_notes = (appointment.notes or '').strip()
    if note not in existing_notes:
        appointment.notes = '\n\n'.join(
            part for part in (note, existing_notes) if part
        )
        appointment.save(update_fields=['notes', 'updated_at'])


# ──────────────────────── PORTAL BOOKING (logged-in) ────────────────────────

@login_required
def portal_book(request):
    """Logged-in user appointment booking."""
    Appointment.cleanup_expired()
    follow_up_id = (
        request.POST.get('follow_up_id')
        or request.GET.get('follow_up')
    )
    followup = None
    selected_pet = None
    if follow_up_id:
        followup = get_object_or_404(
            FollowUp.objects.select_related(
                'appointment__pet',
                'medical_record__pet',
            ).filter(
                Q(appointment__user=request.user)
                | Q(appointment__pet__owner=request.user)
                | Q(medical_record__pet__owner=request.user)
            ),
            pk=follow_up_id,
        )
        if followup.is_completed:
            messages.info(request, 'This follow-up has already been completed.')
            return redirect('appointments:my_appointments')
        if followup.booked_appointment_id and (
            followup.booked_appointment.status != Appointment.Status.CANCELLED
        ):
            return redirect(
                'appointments:portal_detail',
                pk=followup.booked_appointment_id,
            )
        selected_pet = (
            followup.appointment.pet
            if followup.appointment_id else None
        )
        if (
            not selected_pet
            and followup.medical_record_id
            and followup.medical_record.pet.owner_id == request.user.pk
        ):
            selected_pet = followup.medical_record.pet

    if request.method == 'POST':
        with transaction.atomic():
            if followup:
                followup = get_object_or_404(
                    FollowUp.objects.select_for_update(),
                    pk=followup.pk,
                )
                if (
                    not (
                        followup.appointment_id
                        and (
                            followup.appointment.user_id == request.user.pk
                            or (
                                followup.appointment.pet_id
                                and followup.appointment.pet.owner_id
                                == request.user.pk
                            )
                        )
                    )
                    and not (
                        followup.medical_record_id
                        and followup.medical_record.pet.owner_id
                        == request.user.pk
                    )
                ):
                    raise PermissionDenied
                if followup.is_completed:
                    messages.info(
                        request,
                        'This follow-up has already been completed.',
                    )
                    return redirect('appointments:my_appointments')
                if (
                    followup.booked_appointment_id
                    and followup.booked_appointment.status != Appointment.Status.CANCELLED
                ):
                    messages.info(
                        request,
                        'An appointment is already booked for this follow-up.',
                    )
                    return redirect(
                        'appointments:portal_detail',
                        pk=followup.booked_appointment_id,
                    )
            AppointmentService.lock_booking_schedule(
                request.POST.get('branch'),
                request.POST.get('appointment_date'),
            )
            form = PortalAppointmentForm(
                request.POST,
                user=request.user,
                selected_pet=selected_pet,
            )
            appointment = None
            if form.is_valid():
                if (
                    selected_pet
                    and form.cleaned_data.get('selected_pet_id') != selected_pet.pk
                ):
                    form.add_error(
                        None,
                        'Choose the pet linked to this follow-up recommendation.',
                    )
                else:
                    appointment = form.save()
                    if followup:
                        _add_follow_up_booking_note(appointment, followup)
                        followup.booked_appointment = appointment
                        followup.save(update_fields=['booked_appointment'])
        if appointment:
            send_appointment_confirmation(appointment)
            notify_staff_appointment_status_change(
                appointment, appointment.status, actor=request.user
            )
            messages.success(
                request,
                (
                    'Your follow-up appointment has been booked successfully.'
                    if followup
                    else 'Your appointment has been booked successfully!'
                ),
            )
            return redirect('appointments:my_appointments')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        pet_id = request.GET.get('pet')
        if pet_id and not selected_pet:
            try:
                selected_pet = request.user.pets.get(
                    pk=int(pet_id), is_active=True
                )
            except (ValueError, Pet.DoesNotExist):
                selected_pet = None
        form = PortalAppointmentForm(
            user=request.user, selected_pet=selected_pet
        )
        if followup:
            source_appointment = followup.appointment
            source_branch = (
                source_appointment.branch
                if source_appointment else
                followup.medical_record.branch
                if followup.medical_record_id else None
            )
            if source_branch and source_branch.is_active:
                form.initial['branch'] = source_branch.pk
            if followup.follow_up_date >= timezone.localdate():
                form.initial['appointment_date'] = followup.follow_up_date
            if source_appointment and source_appointment.reason_for_visit_id:
                form.initial['reason'] = source_appointment.reason_for_visit_id
            form.initial['pet_symptoms'] = followup.reason

    branches = Branch.objects.filter(is_active=True)
    user_pets = request.user.pets.filter(is_active=True) if hasattr(request.user, 'pets') else []

    return render(request, 'appointments/book_portal.html', {
        'form': form,
        'branches': branches,
        'user_pets': user_pets,
        'followup': followup,
        'selected_pet_id': (
            form.initial.get('selected_pet_id')
            if request.method != 'POST' else None
        ),
    })


@login_required
def my_appointments(request):
    """Show the logged-in user's appointments and follow-ups with tabbed data."""
    # Include pending portal bookings even before a Pet record is created.
    # Pending appointments intentionally keep pet_id empty until staff confirms them.
    base_appts = Appointment.objects.filter(
        user=request.user,
    ).select_related(
        'branch', 'preferred_vet', 'pet', 'pet__owner',
    )

    pending_qs = base_appts.filter(status=Appointment.Status.PENDING)
    confirmed_qs = base_appts.filter(status__in=[
        Appointment.Status.CONFIRMED,
        Appointment.Status.CHECKED_IN,
        Appointment.Status.IN_PROGRESS,
        Appointment.Status.AWAITING_PAYMENT,
    ])
    completed_qs = base_appts.filter(status=Appointment.Status.COMPLETED)
    cancelled_qs = base_appts.filter(status=Appointment.Status.CANCELLED)

    follow_ups_qs = FollowUp.objects.filter(
        Q(appointment__user=request.user)
        | Q(appointment__pet__owner=request.user)
        | Q(medical_record__pet__owner=request.user)
    ).select_related(
        'appointment',
        'appointment__pet',
        'booked_appointment',
    )

    paginated_lists = {}
    for tab_name, queryset in (
        ('pending', pending_qs),
        ('confirmed', confirmed_qs),
        ('followups', follow_ups_qs),
        ('completed', completed_qs),
        ('cancelled', cancelled_qs),
    ):
        paginated_lists[tab_name] = Paginator(queryset, 10).get_page(
            request.GET.get(f'{tab_name}_page', 1),
        )

    active_tab = request.GET.get('tab', 'pending')
    if active_tab not in paginated_lists:
        active_tab = 'pending'

    context = {
        'pending_appts': paginated_lists['pending'],
        'confirmed_appts': paginated_lists['confirmed'],
        'follow_ups': paginated_lists['followups'],
        'completed_appts': paginated_lists['completed'],
        'cancelled_appts': paginated_lists['cancelled'],
        'active_tab': active_tab,
    }
    return render(request, 'appointments/appointments.html', context)


@login_required
def portal_appointment_detail(request, pk):
    """Show an owner's appointment details without exposing staff-only information."""
    appointment = get_object_or_404(
        Appointment.objects.select_related(
            'branch',
            'preferred_vet',
            'reason_for_visit',
            'pet',
            'sale',
        ).prefetch_related(
            'sale__items',
            'sale__payments',
        ),
        pk=pk,
        user=request.user,
    )
    return render(request, 'appointments/portal_detail.html', {
        'appointment': appointment,
        **_portal_appointment_detail_data(appointment),
    })


def _portal_appointment_detail_data(appointment):
    from records.models import RecordEntry

    medical_records = RecordEntry.objects.filter(
        appointment=appointment,
    ).select_related(
        'record',
        'vet',
        'action_required',
    ).order_by('-date_recorded', '-created_at')
    follow_ups = FollowUp.objects.filter(
        appointment=appointment,
    ).select_related('booked_appointment').order_by('-created_at')
    originating_follow_ups = FollowUp.objects.filter(
        booked_appointment=appointment,
    ).select_related('appointment').order_by('-created_at')
    return {
        'medical_records': medical_records,
        'follow_ups': follow_ups,
        'originating_follow_ups': originating_follow_ups,
    }


def _owner_appointment_history_queryset(user, query='', status=''):
    entries = AppointmentHistory.objects.filter(
        owner_visible=True,
        appointment__user=user,
    ).select_related(
        'appointment',
        'appointment__branch',
        'appointment__reason_for_visit',
    ).order_by('-created_at', '-pk')
    if status in Appointment.Status.values:
        entries = entries.filter(appointment__status=status)
    if query:
        for term in query.split():
            status_term = term.replace(' ', '_')
            entries = entries.filter(
                Q(summary__icontains=term)
                | Q(appointment__owner_name__icontains=term)
                | Q(appointment__owner_email__icontains=term)
                | Q(appointment__owner_phone__icontains=term)
                | Q(appointment__pet_name__icontains=term)
                | Q(appointment__pet_species__icontains=term)
                | Q(appointment__pet_breed__icontains=term)
                | Q(appointment__branch__name__icontains=term)
                | Q(appointment__reason_for_visit__name__icontains=term)
                | Q(appointment__status__icontains=status_term)
            )
    return entries


@login_required
def my_appointment_history(request):
    """Show owner-visible history for appointments belonging to this portal user."""
    query = request.GET.get('q', '').strip()
    selected_status = request.GET.get('status', '').strip()
    if selected_status not in Appointment.Status.values:
        selected_status = ''
    entries = _owner_appointment_history_queryset(
        request.user,
        query,
        selected_status,
    )
    page_obj = Paginator(entries, 20).get_page(request.GET.get('page'))
    return render(request, 'appointments/owner_history_list.html', {
        'history_entries': page_obj,
        'page_obj': page_obj,
        'q': query,
        'selected_status': selected_status,
        'statuses': Appointment.Status.choices,
    })


@login_required
@require_GET
def my_appointment_history_search(request):
    """Return owner-scoped appointment history suggestions for the portal search."""
    query = request.GET.get('q', '').strip()
    if len(query) < 2:
        return JsonResponse({'results': []})

    selected_status = request.GET.get('status', '').strip()
    if selected_status not in Appointment.Status.values:
        selected_status = ''
    results = []
    seen_pet_names = set()
    for entry in _owner_appointment_history_queryset(
        request.user,
        query,
        selected_status,
    )[:30]:
        appointment = entry.appointment
        pet_name = appointment.pet_name.strip()
        normalized_name = pet_name.casefold()
        if not normalized_name or normalized_name in seen_pet_names:
            continue
        seen_pet_names.add(normalized_name)
        results.append({
            'value': pet_name,
            'label': pet_name,
            'subtitle': (
                f'{entry.summary} - {appointment.get_status_display()} - '
                f'{appointment.appointment_date.isoformat()}'
            ),
        })
        if len(results) == 8:
            break
    return JsonResponse({'results': results})


@login_required
def my_appointment_history_detail(request, pk):
    """Show one owner-safe history event for the signed-in user's appointment."""
    entry = get_object_or_404(
        AppointmentHistory.objects.select_related(
            'appointment',
            'appointment__branch',
            'appointment__preferred_vet',
            'appointment__reason_for_visit',
        ),
        pk=pk,
        owner_visible=True,
        appointment__user=request.user,
    )
    appointment = get_object_or_404(
        Appointment.objects.select_related(
            'branch',
            'preferred_vet',
            'reason_for_visit',
            'pet',
            'sale',
        ).prefetch_related(
            'sale__items',
            'sale__payments',
        ),
        pk=entry.appointment_id,
        user=request.user,
    )
    entry.visible_changes = [
        change for change in entry.changes
        if change.get('field') in {
            'Status',
            'Date',
            'Time',
            'Branch',
            'Veterinarian',
            'Reason for visit',
        }
    ]
    return render(request, 'appointments/portal_detail.html', {
        'appointment': appointment,
        'history_entry': entry,
        'page_title': 'Appointment History Details',
        **_portal_appointment_detail_data(appointment),
    })


def _staff_appointment_history_queryset(user):
    role_code = getattr(getattr(user, 'assigned_role', None), 'code', '')
    if role_code not in StaffRoles.ALL_STAFF_ROLES:
        raise PermissionDenied

    appointments = Appointment.objects.all()
    is_veterinarian = role_code in (
        StaffRoles.VETERINARIAN,
        StaffRoles.VET_ASSISTANT,
    )
    appointments = _scope_view_only_appointments(
        user,
        appointments,
        include_unassigned=is_veterinarian,
    )
    is_branch_restricted = (
        user.is_module_branch_restricted('appointments')
        or is_veterinarian
    )
    if is_branch_restricted:
        if not user.branch_id:
            raise PermissionDenied
        appointments = appointments.filter(branch_id=user.branch_id)
    if is_veterinarian:
        try:
            staff_profile = user.staff_profile
        except StaffMember.DoesNotExist:
            raise PermissionDenied
        appointments = appointments.filter(
            Q(preferred_vet=staff_profile)
            | Q(preferred_vet__isnull=True)
        )
    return appointments


@login_required
@module_permission_required('appointments', 'VIEW')
def admin_appointment_history(request):
    """Show history only for appointments the current staff member may access."""
    appointments = _staff_appointment_history_queryset(request.user)
    entries = AppointmentHistory.objects.filter(
        appointment__in=appointments,
    ).select_related(
        'appointment',
        'appointment__branch',
        'actor',
    ).order_by('-created_at', '-pk')
    page_obj = Paginator(entries, 20).get_page(request.GET.get('page'))
    return render(request, 'appointments/admin_history_list.html', {
        'history_entries': page_obj,
        'page_obj': page_obj,
    })


@login_required
@module_permission_required('appointments', 'VIEW')
def admin_appointment_history_detail(request, pk):
    """Show one full audit event, scoped to the staff member's appointment access."""
    appointments = _staff_appointment_history_queryset(request.user)
    entry = get_object_or_404(
        AppointmentHistory.objects.select_related(
            'appointment',
            'appointment__branch',
            'appointment__preferred_vet',
            'appointment__reason_for_visit',
            'actor',
        ),
        pk=pk,
        appointment__in=appointments,
    )
    return render(request, 'appointments/admin_history_detail.html', {
        'history_entry': entry,
    })


@login_required
@require_POST
def portal_cancel(request, pk):
    """Allow owners to cancel pending or confirmed appointments at least 24 hours ahead."""
    with transaction.atomic():
        appointment = get_object_or_404(
            Appointment.objects.select_for_update(),
            pk=pk,
            user=request.user,
        )
        if not appointment.owner_can_cancel:
            messages.error(
                request,
                'This appointment can no longer be cancelled from the owner portal.',
            )
            return redirect('appointments:my_appointments')

        form = AppointmentCancellationForm(request.POST)
        if not form.is_valid():
            messages.error(
                request,
                'Enter a cancellation reason with at least five characters.',
            )
            return redirect('appointments:my_appointments')

        appointment.status = Appointment.Status.CANCELLED
        appointment.cancellation_reason = form.cleaned_data['cancellation_reason']
        appointment.save(update_fields=[
            'status', 'cancellation_reason', 'updated_at',
        ])

    notify_appointment_status_change(
        appointment, appointment.status, actor=request.user,
    )
    notify_staff_appointment_status_change(
        appointment, appointment.status, actor=request.user,
    )
    messages.success(request, 'Your appointment has been cancelled.')
    return redirect('appointments:my_appointments')


# ──────────────────────── AJAX API ENDPOINTS ────────────────────────

@require_GET
def api_available_vets(request):
    """Return available vets and vet assistants for a given branch and date."""
    branch_id = request.GET.get('branch')
    appt_date = request.GET.get('date')

    if not branch_id:
        return JsonResponse({'vets': []})

    # Schedulable roles: veterinarians and vet assistants
    schedulable_roles = ['veterinarian', 'assistant_veterinarian']

    # If a date is provided, only return staff who have a schedule that day
    if appt_date:
        scheduled_staff_ids = VetSchedule.objects.filter(
            branch_id=branch_id,
            date=appt_date,
            is_available=True,
            start_time__lt=CLINIC_CLOSE_TIME,
            end_time__gt=CLINIC_OPEN_TIME,
            staff__user__assigned_role__code__in=schedulable_roles,
        ).values_list('staff_id', flat=True).distinct()

        # Only return vets/vet assistants who are actually scheduled on this date
        vets = StaffMember.objects.filter(
            id__in=scheduled_staff_ids,
            user__assigned_role__code__in=schedulable_roles,
            user__is_active=True,
            is_active=True,
        ).select_related('user', 'user__assigned_role')
    else:
        # No date provided - return all vets/vet assistants assigned to this branch
        vets = StaffMember.objects.filter(
            user__assigned_role__code__in=schedulable_roles,
            user__is_active=True,
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

    schedulable_roles = ['veterinarian', 'assistant_veterinarian']
    filters = {
        'date': target_date,
        'is_available': True,
        'start_time__lt': CLINIC_CLOSE_TIME,
        'end_time__gt': CLINIC_OPEN_TIME,
        'staff__is_active': True,
        'staff__user__is_active': True,
        'staff__user__assigned_role__code__in': schedulable_roles,
    }
    if branch_id:
        try:
            filters['branch_id'] = int(branch_id)
        except (ValueError, TypeError):
            pass
    if vet_id:
        try:
            filters['staff_id'] = int(vet_id)
        except (ValueError, TypeError):
            filters['staff_id'] = vet_id

    has_scheduled_vets = VetSchedule.objects.filter(**filters).exists()
    
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
    """Return dates with at least one available vet schedule for a month."""
    vet_id = request.GET.get('vet')
    year = request.GET.get('year')
    month = request.GET.get('month')
    branch_id = request.GET.get('branch')

    if not (year and month):
        return JsonResponse({'dates': []})

    try:
        year = int(year)
        month = int(month)
    except (ValueError, TypeError):
        return JsonResponse({'dates': []})

    if month < 1 or month > 12:
        return JsonResponse({'dates': []})

    _, last_day = cal_mod.monthrange(year, month)

    filters = {
        'date__gte': date(year, month, 1),
        'date__lte': date(year, month, last_day),
        'is_available': True,
        'start_time__lt': CLINIC_CLOSE_TIME,
        'end_time__gt': CLINIC_OPEN_TIME,
        'staff__is_active': True,
        'staff__user__is_active': True,
        'staff__user__assigned_role__code__in': ['veterinarian', 'assistant_veterinarian'],
    }
    if vet_id:
        filters['staff_id'] = vet_id
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

def _workflow_appointment_for_staff(request, pk, *, veterinarian=False):
    """Return an appointment inside the caller's permitted branch and role scope."""
    appointment = get_object_or_404(
        Appointment.objects.select_for_update(of=('self',)).select_related(
            'branch', 'preferred_vet', 'sale',
        ),
        pk=pk,
    )
    role_code = getattr(getattr(request.user, 'assigned_role', None), 'code', '')
    if veterinarian:
        if role_code not in ('veterinarian', 'assistant_veterinarian'):
            raise PermissionDenied
        if not request.user.has_module_permission('appointments', 'VIEW'):
            raise PermissionDenied
        try:
            staff_profile = request.user.staff_profile
        except StaffMember.DoesNotExist:
            raise PermissionDenied
        if (
            not request.user.branch_id
            or appointment.branch_id != request.user.branch_id
            or (
                appointment.preferred_vet_id
                and appointment.preferred_vet_id != staff_profile.pk
            )
        ):
            raise PermissionDenied
    else:
        if not request.user.has_module_permission('appointments', 'EDIT'):
            raise PermissionDenied
        if (
            request.user.is_module_branch_restricted('appointments')
            and appointment.branch_id != request.user.branch_id
        ):
            raise PermissionDenied
    return appointment


@login_required
@require_POST
@transaction.atomic
def admin_workflow_action(request, pk, action):
    """Apply receptionist-only appointment lifecycle transitions."""
    appointment = _workflow_appointment_for_staff(request, pk)
    detail_url = 'appointments:admin_detail'
    original_status = appointment.status

    if action == 'confirm':
        if original_status != Appointment.Status.PENDING:
            messages.error(request, 'Only pending appointments can be confirmed.')
            return redirect(detail_url, pk=pk)
        appointment.status = Appointment.Status.CONFIRMED
    elif action == 'check-in':
        if original_status != Appointment.Status.CONFIRMED:
            messages.error(request, 'Only confirmed appointments can be checked in.')
            return redirect(detail_url, pk=pk)
        if appointment.appointment_date > timezone.localdate():
            messages.error(
                request,
                'This appointment cannot be checked in before its scheduled date.',
            )
            return redirect(detail_url, pk=pk)
        appointment.status = Appointment.Status.CHECKED_IN
        appointment.checked_in_at = timezone.now()
    elif action == 'cancel':
        if original_status not in (
            Appointment.Status.PENDING,
            Appointment.Status.CONFIRMED,
            Appointment.Status.CHECKED_IN,
        ):
            messages.error(request, 'This appointment can no longer be cancelled.')
            return redirect(detail_url, pk=pk)
        form = AppointmentCancellationForm(request.POST)
        if not form.is_valid():
            messages.error(
                request,
                'Enter a cancellation reason with at least five characters.',
            )
            return redirect(detail_url, pk=pk)
        appointment.status = Appointment.Status.CANCELLED
        appointment.cancellation_reason = form.cleaned_data['cancellation_reason']
    elif action == 'complete':
        if original_status != Appointment.Status.AWAITING_PAYMENT:
            messages.error(request, 'The veterinarian must hand off this visit first.')
            return redirect(detail_url, pk=pk)
        if not appointment.sale_id or appointment.sale.status != 'COMPLETED':
            messages.error(request, 'Complete the linked POS payment before closing this visit.')
            return redirect(detail_url, pk=pk)
        if appointment.medical_record_decision == Appointment.MedicalRecordDecision.UNDECIDED:
            messages.error(request, 'The veterinarian must resolve the medical-record decision.')
            return redirect(detail_url, pk=pk)
        if (
            appointment.medical_record_decision == Appointment.MedicalRecordDecision.REQUIRED
            and not appointment.record_entries.exists()
        ):
            messages.error(request, 'Save the required medical record before completing this visit.')
            return redirect(detail_url, pk=pk)
        appointment.status = Appointment.Status.COMPLETED
    else:
        raise PermissionDenied

    appointment.save()
    if action == 'complete':
        FollowUp.objects.filter(
            booked_appointment=appointment,
            is_completed=False,
        ).update(is_completed=True)
    if appointment.user:
        notify_appointment_status_change(
            appointment, appointment.status, actor=request.user,
        )
    notify_staff_appointment_status_change(
        appointment, appointment.status, actor=request.user,
    )
    messages.success(
        request,
        f'{appointment.pet_name} appointment updated to {appointment.get_status_display()}.',
    )
    return redirect(detail_url, pk=pk)


@login_required
@module_permission_required('appointments', 'VIEW')
def admin_detail(request, pk):
    """Show the full appointment workflow and role-appropriate next actions."""
    role_code = getattr(getattr(request.user, 'assigned_role', None), 'code', '')
    is_veterinarian = role_code in (
        'veterinarian',
        'assistant_veterinarian',
    )
    appointments = Appointment.objects.select_related(
        'branch',
        'preferred_vet',
        'user',
        'sale',
    ).prefetch_related(
        'sale__items',
        'sale__payments',
    )

    if is_veterinarian:
        try:
            staff_profile = request.user.staff_profile
        except StaffMember.DoesNotExist:
            raise PermissionDenied
        if not request.user.branch_id:
            raise PermissionDenied
        appointments = appointments.filter(
            pk=pk,
            branch_id=request.user.branch_id,
        ).filter(
            Q(preferred_vet=staff_profile) | Q(preferred_vet__isnull=True)
        )
    else:
        if (
            request.user.is_module_branch_restricted('appointments')
            and not request.user.branch_id
        ):
            raise PermissionDenied
        if request.user.is_module_branch_restricted('appointments'):
            appointments = appointments.filter(
                branch_id=request.user.branch_id,
            )
        has_management_permission = any(
            request.user.has_module_permission('appointments', permission)
            for permission in ('CREATE', 'EDIT', 'DELETE')
        )
        if not has_management_permission:
            appointments = _scope_view_only_appointments(
                request.user,
                appointments,
            )

    appointment = get_object_or_404(appointments, pk=pk)
    from records.models import RecordEntry
    record_entries = list(
        RecordEntry.objects.filter(appointment=appointment)
        .select_related('record', 'vet')
        .order_by('-date_recorded', '-created_at')
    )
    appointment.medical_record_added = bool(record_entries)
    follow_ups = FollowUp.objects.filter(
        appointment=appointment,
    ).select_related('booked_appointment').order_by('-created_at')
    originating_follow_ups = FollowUp.objects.filter(
        booked_appointment=appointment,
    ).select_related('appointment').order_by('-created_at')

    can_edit = (
        request.user.has_module_permission('appointments', 'EDIT')
        and not is_veterinarian
    )
    can_manage_workflow = can_edit
    can_delete = (
        request.user.has_module_permission('appointments', 'DELETE')
        and not is_veterinarian
    )
    can_create_medical_record = request.user.has_module_permission(
        'medical_records', 'CREATE'
    )
    can_create_appointment = request.user.has_module_permission(
        'appointments', 'CREATE'
    )
    can_book_followup = (
        can_create_appointment
        and (
            not request.user.is_module_branch_restricted('appointments')
            or appointment.branch_id == request.user.branch_id
        )
    )
    can_access_pos = request.user.has_special_permission('can_access_pos')
    appointment_date_arrived = (
        appointment.appointment_date <= timezone.localdate()
    )
    can_check_in = (
        can_manage_workflow
        and appointment.status == Appointment.Status.CONFIRMED
        and appointment_date_arrived
    )
    can_start_visit = (
        is_veterinarian
        and appointment_date_arrived
        and appointment.status in (
            Appointment.Status.CONFIRMED,
            Appointment.Status.CHECKED_IN,
        )
    )
    can_decide_record = (
        is_veterinarian
        and appointment.status == Appointment.Status.IN_PROGRESS
        and appointment.medical_record_decision
        == Appointment.MedicalRecordDecision.UNDECIDED
    )
    can_send_to_payment = (
        is_veterinarian
        and appointment.status == Appointment.Status.IN_PROGRESS
        and appointment.medical_record_decision
        == Appointment.MedicalRecordDecision.REQUIRED
        and appointment.medical_record_added
    )
    can_cancel = (
        can_manage_workflow
        and appointment.status in (
            Appointment.Status.PENDING,
            Appointment.Status.CONFIRMED,
            Appointment.Status.CHECKED_IN,
        )
    )
    can_complete = (
        can_manage_workflow
        and appointment.status == Appointment.Status.AWAITING_PAYMENT
        and appointment.sale_id
        and appointment.sale.status == 'COMPLETED'
        and appointment.medical_record_decision
        != Appointment.MedicalRecordDecision.UNDECIDED
        and (
            appointment.medical_record_decision
            != Appointment.MedicalRecordDecision.REQUIRED
            or appointment.medical_record_added
        )
    )
    return render(request, 'appointments/admin_detail.html', {
        'appointment': appointment,
        'record_entries': record_entries,
        'follow_ups': follow_ups,
        'originating_follow_ups': originating_follow_ups,
        'is_veterinarian': is_veterinarian,
        'can_edit': can_edit,
        'can_manage_workflow': can_manage_workflow,
        'can_delete': can_delete,
        'can_create_medical_record': can_create_medical_record,
        'can_create_appointment': can_create_appointment,
        'can_book_followup': can_book_followup,
        'can_access_pos': can_access_pos,
        'appointment_date_arrived': appointment_date_arrived,
        'can_check_in': can_check_in,
        'can_start_visit': can_start_visit,
        'can_decide_record': can_decide_record,
        'can_send_to_payment': can_send_to_payment,
        'can_cancel': can_cancel,
        'can_complete': can_complete,
    })


@login_required
@require_POST
@transaction.atomic
def veterinarian_workflow_action(request, pk, action):
    """Apply veterinarian-only visit and medical-record decision transitions."""
    appointment = _workflow_appointment_for_staff(request, pk, veterinarian=True)
    if action == 'start':
        if appointment.status not in (
            Appointment.Status.CONFIRMED,
            Appointment.Status.CHECKED_IN,
        ):
            messages.error(request, 'Only confirmed or checked-in appointments can be started.')
            return redirect('appointments:admin_detail', pk=pk)
        if appointment.appointment_date > timezone.localdate():
            messages.error(
                request,
                'The consultation cannot start before the scheduled appointment date.',
            )
            return redirect('appointments:admin_detail', pk=pk)
        appointment.status = Appointment.Status.IN_PROGRESS
        appointment.visit_started_at = timezone.now()
        if not appointment.preferred_vet_id:
            appointment.preferred_vet = request.user.staff_profile
    elif action == 'record-required':
        if appointment.status != Appointment.Status.IN_PROGRESS:
            messages.error(request, 'Start this visit before choosing its record requirement.')
            return redirect('appointments:admin_detail', pk=pk)
        appointment.medical_record_decision = Appointment.MedicalRecordDecision.REQUIRED
        appointment.medical_record_decision_reason = ''
    elif action == 'no-record':
        if appointment.status != Appointment.Status.IN_PROGRESS:
            messages.error(request, 'Start this visit before choosing its record requirement.')
            return redirect('appointments:admin_detail', pk=pk)
        reason = request.POST.get('medical_record_decision_reason', '').strip()
        if len(reason) < 5:
            messages.error(request, 'Explain why no medical record is required (at least five characters).')
            return redirect('appointments:admin_detail', pk=pk)

        follow_up_enabled = request.POST.get('follow_up_enabled') == 'on'
        followup = None
        follow_up_date = None
        follow_up_end_date = None
        follow_up_reason = request.POST.get('follow_up_reason', '').strip()
        if follow_up_enabled:
            try:
                follow_up_date = date.fromisoformat(
                    request.POST.get('follow_up_date', ''),
                )
                follow_up_end_date_value = request.POST.get(
                    'follow_up_end_date', '',
                ).strip()
                follow_up_end_date = (
                    date.fromisoformat(follow_up_end_date_value)
                    if follow_up_end_date_value else None
                )
            except ValueError:
                messages.error(
                    request,
                    'Enter a valid follow-up date and optional end date.',
                )
                return redirect('appointments:admin_detail', pk=pk)
            if follow_up_date < timezone.localdate():
                messages.error(
                    request,
                    'The recommended follow-up date cannot be in the past.',
                )
                return redirect('appointments:admin_detail', pk=pk)
            if follow_up_end_date and follow_up_end_date < follow_up_date:
                messages.error(
                    request,
                    'The follow-up end date cannot be before its start date.',
                )
                return redirect('appointments:admin_detail', pk=pk)

        appointment.medical_record_decision = Appointment.MedicalRecordDecision.NOT_REQUIRED
        appointment.medical_record_decision_reason = reason
        appointment.status = Appointment.Status.AWAITING_PAYMENT
    elif action == 'send-to-payment':
        if (
            appointment.status != Appointment.Status.IN_PROGRESS
            or appointment.medical_record_decision
            != Appointment.MedicalRecordDecision.REQUIRED
            or not appointment.record_entries.exists()
        ):
            messages.error(request, 'Save the required medical record before sending this visit to POS.')
            return redirect('appointments:admin_detail', pk=pk)
        appointment.status = Appointment.Status.AWAITING_PAYMENT
    else:
        raise PermissionDenied

    appointment.save()
    if action == 'no-record' and follow_up_enabled:
        followup = FollowUp.objects.filter(
            appointment=appointment,
            booked_appointment__isnull=True,
            is_completed=False,
        ).order_by('-created_at').first()
        event = 'updated' if followup else 'scheduled'
        if not followup:
            followup = FollowUp(
                appointment=appointment,
                pet_name=appointment.pet_name,
                created_by=request.user,
            )
        followup.follow_up_date = follow_up_date
        followup.follow_up_end_date = follow_up_end_date
        followup.reason = follow_up_reason
        followup.email_sent_at = None
        followup.reminder_email_sent_at = None
        followup.email_attempts = 0
        followup.email_last_error = ''
        followup.save()
        notify_follow_up_scheduled(
            appointment=appointment,
            followup=followup,
            follow_up_reason=follow_up_reason,
            event=event,
        )

    if action == 'start':
        notify_veterinarian_consultation_started(appointment)
    else:
        if appointment.user:
            notify_appointment_status_change(
                appointment, appointment.status, actor=request.user,
            )
        notify_staff_appointment_status_change(
            appointment, appointment.status, actor=request.user,
        )
    messages.success(
        request,
        f'{appointment.pet_name} visit updated to {appointment.get_status_display()}.',
    )
    return redirect('appointments:admin_detail', pk=pk)


@login_required
@module_permission_required('appointments', 'VIEW')
def admin_list(request):
    """Admin view: list all appointments with filters + calendar support."""
    Appointment.cleanup_expired()

    appointments = Appointment.objects.select_related(
        'branch', 'preferred_vet', 'user').all()
    role_code = getattr(getattr(request.user, 'assigned_role', None), 'code', '')
    is_veterinarian = role_code in (
        'veterinarian',
        'assistant_veterinarian',
    )
    appointments = _scope_view_only_appointments(
        request.user,
        appointments,
        include_unassigned=is_veterinarian,
    )

    # Check if user is branch-restricted for appointments
    is_branch_restricted = (
        request.user.is_module_branch_restricted('appointments')
        or is_veterinarian
    )
    user_branch = request.user.branch
    
    # If branch restricted, filter appointments to user's branch only
    if is_branch_restricted and user_branch:
        appointments = appointments.filter(branch=user_branch)
    if is_veterinarian:
        try:
            staff_profile = request.user.staff_profile
        except StaffMember.DoesNotExist:
            appointments = appointments.none()
        else:
            if not user_branch:
                appointments = appointments.none()
            else:
                appointments = appointments.filter(
                    Q(preferred_vet=staff_profile)
                    | Q(preferred_vet__isnull=True)
                )

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
    # If user is branch-restricted, only show vets from their branch
    vets_query = StaffMember.objects.filter(
        user__assigned_role__code__in=['veterinarian', 'assistant_veterinarian'],
        user__is_active=True,
        is_active=True,
    )
    
    if is_branch_restricted and user_branch:
        vets_query = vets_query.filter(branch=user_branch)
    
    vets = vets_query.select_related('user', 'user__assigned_role')
    followup_booking = None
    followup_booking_data = None
    quick_initial = {'status': Appointment.Status.CONFIRMED}
    follow_up_id = request.GET.get('follow_up')
    if follow_up_id:
        if not request.user.has_module_permission('appointments', 'CREATE'):
            raise PermissionDenied
        followup_booking = get_object_or_404(
            FollowUp.objects.select_related(
                'appointment__pet',
                'appointment__user',
                'appointment__branch',
                'appointment__reason_for_visit',
                'medical_record__pet',
                'medical_record__pet__owner',
                'medical_record__branch',
            ).filter(is_completed=False).filter(
                Q(booked_appointment__isnull=True)
                | Q(booked_appointment__status=Appointment.Status.CANCELLED)
            ),
            pk=follow_up_id,
        )
        source_appointment = followup_booking.appointment
        followup_pet = (
            source_appointment.pet
            if source_appointment else
            followup_booking.medical_record.pet
            if followup_booking.medical_record_id else None
        )
        followup_owner = (
            source_appointment.user
            if source_appointment and source_appointment.user_id
            else followup_pet.owner if followup_pet else None
        )
        source_branch = (
            source_appointment.branch
            if source_appointment else
            followup_booking.medical_record.branch
            if followup_booking.medical_record_id else
            followup_pet.branch if followup_pet else None
        )
        if (
            is_branch_restricted
            and (
                not user_branch
                or not source_branch
                or source_branch.pk != user_branch.pk
            )
        ):
            raise PermissionDenied

        owner_name = (
            source_appointment.current_owner_name
            if source_appointment else
            followup_pet.owner_display_name if followup_pet else ''
        )
        owner_email = (
            source_appointment.current_owner_email
            if source_appointment else
            followup_pet.owner_display_email if followup_pet else ''
        )
        owner_phone = (
            source_appointment.current_owner_phone
            if source_appointment else
            followup_pet.owner_display_phone if followup_pet else ''
        )
        owner_address = (
            source_appointment.current_owner_address
            if source_appointment else
            followup_pet.owner_display_address if followup_pet else ''
        )
        if owner_name == '—':
            owner_name = ''
        if owner_email == '—':
            owner_email = ''
        if owner_phone == '—':
            owner_phone = ''
        if owner_address == '—':
            owner_address = ''

        quick_initial.update({
            'source': (
                Appointment.Source.PORTAL
                if followup_owner else Appointment.Source.WALKIN
            ),
            'owner_name': owner_name,
            'owner_email': owner_email,
            'owner_phone': owner_phone,
            'owner_address': owner_address,
            'pet_name': followup_pet.name if followup_pet else followup_booking.pet_name,
            'pet_species': followup_pet.species if followup_pet else source_appointment.pet_species,
            'pet_breed': followup_pet.breed if followup_pet else source_appointment.pet_breed,
            'pet_dob': followup_pet.date_of_birth if followup_pet else source_appointment.pet_dob,
            'pet_sex': followup_pet.sex if followup_pet else source_appointment.pet_sex,
            'pet_color': followup_pet.color if followup_pet else source_appointment.pet_color,
            'branch': user_branch.pk if is_branch_restricted and user_branch else (
                source_branch.pk if source_branch else None
            ),
            'appointment_date': max(
                followup_booking.follow_up_date,
                timezone.localdate(),
            ),
            'reason': (
                source_appointment.reason_for_visit_id
                if source_appointment else None
            ),
            'notes': followup_booking.reason,
            'selected_user_id': followup_owner.pk if followup_owner else None,
            'selected_pet_id': (
                followup_pet.pk if followup_pet else None
            ),
        })
        followup_booking_data = {
            'source': quick_initial['source'],
            'user_id': followup_owner.pk if followup_owner else '',
            'pet_id': followup_pet.pk if followup_pet else '',
            'owner_name': quick_initial['owner_name'] or '',
            'owner_email': quick_initial['owner_email'] or '',
            'owner_phone': quick_initial['owner_phone'] or '',
            'owner_address': quick_initial['owner_address'] or '',
            'pet_name': quick_initial['pet_name'] or '',
            'pet_species': quick_initial['pet_species'] or '',
            'pet_breed': quick_initial['pet_breed'] or '',
            'pet_dob': (
                followup_pet.date_of_birth.isoformat()
                if followup_pet and followup_pet.date_of_birth else ''
            ),
            'pet_sex': quick_initial['pet_sex'] or '',
            'pet_color': quick_initial['pet_color'] or '',
            'follow_up_id': followup_booking.pk,
        }
    quick_form = AdminQuickCreateForm(initial=quick_initial, user=request.user)

    # Pagination (only for table view)
    page_number = request.GET.get('page', 1)
    paginator = Paginator(appointments, 10)
    page_obj = paginator.get_page(page_number)

    page_appointments = list(page_obj.object_list)
    from records.models import RecordEntry
    record_appointment_ids = set(
        RecordEntry.objects.filter(
            appointment_id__in=[
                appointment.pk for appointment in page_appointments
                if appointment.status in (
                    Appointment.Status.IN_PROGRESS,
                    Appointment.Status.AWAITING_PAYMENT,
                    Appointment.Status.COMPLETED,
                )
            ],
        ).values_list('appointment_id', flat=True)
    )
    for appointment in page_appointments:
        appointment.medical_record_added = appointment.pk in record_appointment_ids
        appointment.can_vet_workflow = (
            is_veterinarian
            and appointment.status in (
                Appointment.Status.CONFIRMED,
                Appointment.Status.CHECKED_IN,
                Appointment.Status.IN_PROGRESS,
            )
        )

    # Check permissions for CRUD buttons
    can_create = request.user.has_module_permission('appointments', 'CREATE')
    can_edit = request.user.has_module_permission('appointments', 'EDIT')
    can_delete = request.user.has_module_permission('appointments', 'DELETE')
    can_create_medical_record = request.user.has_module_permission(
        'medical_records', 'CREATE'
    )
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
        'followup_booking': followup_booking,
        'followup_booking_data': followup_booking_data,
        'is_branch_restricted': is_branch_restricted,
        'user_branch': user_branch,
        'can_create': can_create,
        'can_edit': can_edit,
        'can_delete': can_delete,
        'can_create_medical_record': can_create_medical_record,
        'is_veterinarian': is_veterinarian,
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
    role_code = getattr(getattr(request.user, 'assigned_role', None), 'code', '')
    is_veterinarian = role_code in (
        'veterinarian',
        'assistant_veterinarian',
    )
    appointments = _scope_view_only_appointments(
        request.user,
        appointments,
        include_unassigned=is_veterinarian,
    )

    # Check if user is branch-restricted for appointments
    is_branch_restricted = (
        request.user.is_module_branch_restricted('appointments')
        or is_veterinarian
    )
    user_branch = request.user.branch
    
    # If branch restricted, filter appointments to user's branch only
    if is_branch_restricted and user_branch:
        appointments = appointments.filter(branch=user_branch)
    if is_veterinarian:
        try:
            staff_profile = request.user.staff_profile
        except StaffMember.DoesNotExist:
            appointments = appointments.none()
        else:
            if not user_branch:
                appointments = appointments.none()
            else:
                appointments = appointments.filter(
                    Q(preferred_vet=staff_profile)
                    | Q(preferred_vet__isnull=True)
                )

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

    source = request.GET.get('source')
    if source:
        appointments = appointments.filter(source=source)

    events = []
    for a in appointments:
        # Get pet clinical data if linked
        pet_clinical_status = None
        pet_clinical_display = None
        if a.pet:
            pet_clinical_status = a.pet.clinical_status.code if a.pet.clinical_status else None
            pet_clinical_display = a.pet.status_display

        events.append({
            'id': a.id,
            'petId': a.pet.id if a.pet else None,
            'petName': a.pet_name or '',
            'petBreed': a.pet_breed or '',
            'petSpecies': a.pet_species or 'Unknown',
            'petDOB': a.pet.date_of_birth.isoformat() if a.pet and a.pet.date_of_birth else None,
            'petSex': a.pet.sex if a.pet and a.pet.sex else '',
            'petColor': a.pet.color if a.pet and a.pet.color else '',
            'petClinicalStatus': pet_clinical_status,
            'petClinicalDisplay': pet_clinical_display,
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
            'vetName': (
                a.preferred_vet.full_name
                if getattr(a, 'preferred_vet', None) else 'Unassigned'
            ),
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
        followup = None
        with transaction.atomic():
            follow_up_id = request.POST.get('follow_up_id')
            if follow_up_id:
                followup = get_object_or_404(
                    FollowUp.objects.select_for_update(),
                    pk=follow_up_id,
                )
                if followup.is_completed or (
                    followup.booked_appointment_id
                    and followup.booked_appointment.status
                    != Appointment.Status.CANCELLED
                ):
                    messages.error(
                        request,
                        'This follow-up already has an active or completed visit.',
                    )
                    return redirect('appointments:admin_list')
                source_appointment = followup.appointment
                followup_pet = (
                    source_appointment.pet
                    if source_appointment else
                    followup.medical_record.pet
                    if followup.medical_record_id else None
                )
                source_branch = (
                    source_appointment.branch
                    if source_appointment else
                    followup.medical_record.branch
                    if followup.medical_record_id else
                    followup_pet.branch if followup_pet else None
                )
                if request.user.is_module_branch_restricted('appointments'):
                    if (
                        not request.user.branch_id
                        or not source_branch
                        or source_branch.pk != request.user.branch_id
                        or request.POST.get('branch')
                        != str(request.user.branch_id)
                    ):
                        raise PermissionDenied
            AppointmentService.lock_booking_schedule(
                request.POST.get('branch'),
                request.POST.get('appointment_date'),
            )
            form = AdminQuickCreateForm(request.POST, user=request.user)
            appointment = form.save() if form.is_valid() else None
            if appointment and followup:
                source_appointment = followup.appointment
                followup_pet = (
                    source_appointment.pet
                    if source_appointment else
                    followup.medical_record.pet
                    if followup.medical_record_id else None
                )
                appointment.owner_name = (
                    source_appointment.current_owner_name
                    if source_appointment else
                    followup_pet.owner_display_name if followup_pet else
                    appointment.owner_name
                )
                appointment.owner_email = (
                    source_appointment.current_owner_email
                    if source_appointment else
                    followup_pet.owner_display_email if followup_pet else
                    appointment.owner_email
                )
                appointment.owner_phone = (
                    source_appointment.current_owner_phone
                    if source_appointment else
                    followup_pet.owner_display_phone if followup_pet else
                    appointment.owner_phone
                )
                appointment.owner_address = (
                    source_appointment.current_owner_address
                    if source_appointment else
                    followup_pet.owner_display_address if followup_pet else
                    appointment.owner_address
                )
                appointment.user = (
                    source_appointment.user
                    if source_appointment and source_appointment.user_id
                    else followup_pet.owner if followup_pet else None
                )
                if followup_pet:
                    appointment.pet = followup_pet
                    appointment.pet_name = followup_pet.name
                    appointment.pet_species = followup_pet.species
                    appointment.pet_breed = followup_pet.breed
                _add_follow_up_booking_note(appointment, followup)
                appointment.save(update_fields=[
                    'owner_name',
                    'owner_email',
                    'owner_phone',
                    'owner_address',
                    'user',
                    'pet',
                    'pet_name',
                    'pet_species',
                    'pet_breed',
                    'updated_at',
                ])
                followup.booked_appointment = appointment
                followup.save(update_fields=['booked_appointment'])
        if appointment:

            # Send email confirmation
            send_appointment_confirmation(appointment)

            # Notify user if appointment is confirmed and has a linked user
            if appointment.status == 'CONFIRMED' and appointment.user:
                notify_appointment_status_change(appointment, 'CONFIRMED', actor=request.user)
            
            # Also notify vet assistants about the appointment status
            notify_staff_appointment_status_change(appointment, appointment.status, actor=request.user)
            if appointment.status == Appointment.Status.COMPLETED:
                notify_veterinarian_medical_record_required(appointment, actor=request.user)

            messages.success(
                request,
                (
                    'Follow-up appointment booked successfully.'
                    if followup
                    else 'Appointment created successfully.'
                ),
            )
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
        with transaction.atomic():
            appointment = get_object_or_404(
                Appointment.objects.select_for_update(),
                pk=pk,
            )
            original_status = appointment.status
            AppointmentService.lock_booking_schedule(
                request.POST.get('branch'),
                request.POST.get('appointment_date'),
            )
            form = AppointmentEditForm(
                request.POST, instance=appointment, user=request.user,
            )
            updated_appointment = form.save() if form.is_valid() else None
        if updated_appointment:
            # Sync / update the linked Patient record with any edited pet details
            from appointments.utils import sync_pet_from_appointment
            sync_pet_from_appointment(updated_appointment)

            # Check if status changed and notify user
            if updated_appointment.status != original_status and updated_appointment.user:
                notify_appointment_status_change(
                    updated_appointment,
                    updated_appointment.status,
                    actor=request.user,
                )
            
            # Also notify vet assistants about the appointment status change
            if updated_appointment.status != original_status:
                notify_staff_appointment_status_change(
                    updated_appointment,
                    updated_appointment.status,
                    actor=request.user,
                )
                if updated_appointment.status == Appointment.Status.COMPLETED:
                    notify_veterinarian_medical_record_required(
                        updated_appointment,
                        actor=request.user,
                    )

            # Handle follow-up creation
            follow_up_enabled = request.POST.get('follow_up_enabled')
            if follow_up_enabled == 'on':
                follow_up_date = request.POST.get('follow_up_date')
                follow_up_end_date = request.POST.get('follow_up_end_date')
                follow_up_reason = request.POST.get('follow_up_reason', '')
                if follow_up_date:
                    followup = FollowUp.objects.filter(
                        appointment=updated_appointment,
                    ).order_by('-created_at').first()
                    event = 'updated' if followup else 'scheduled'
                    if followup:
                        followup.pet_name = updated_appointment.pet_name
                        followup.follow_up_date = follow_up_date
                        followup.follow_up_end_date = follow_up_end_date or None
                        followup.reason = follow_up_reason
                        followup.email_sent_at = None
                        followup.reminder_email_sent_at = None
                        followup.email_attempts = 0
                        followup.email_last_error = ''
                        followup.save()
                    else:
                        followup = FollowUp.objects.create(
                            appointment=updated_appointment,
                            pet_name=updated_appointment.pet_name,
                            follow_up_date=follow_up_date,
                            follow_up_end_date=follow_up_end_date if follow_up_end_date else None,
                            reason=follow_up_reason,
                            created_by=request.user,
                        )

                    sync_appointment_follow_up_to_medical_record(
                        updated_appointment, followup,
                    )
                    notify_follow_up_scheduled(
                        appointment=updated_appointment,
                        followup=followup,
                        follow_up_reason=follow_up_reason,
                        event=event,
                    )

                    date_str = str(follow_up_date)
                    if follow_up_end_date and follow_up_end_date != follow_up_date:
                        date_str = f"{follow_up_date} to {follow_up_end_date}"
                    messages.info(
                            request, f'Follow-up recommended for {date_str}.')

            messages.success(
                request, f'Appointment for {updated_appointment.pet_name} updated.')
            return redirect('appointments:admin_list')
    else:
        form = AppointmentEditForm(instance=appointment, user=request.user)

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
@transaction.atomic
def admin_delete(request, pk):
    """Allow staff to delete cancelled appointments after notifying the owner."""
    appointment = get_object_or_404(
        Appointment.objects.select_for_update(),
        pk=pk,
    )
    if appointment.status != Appointment.Status.CANCELLED:
        messages.error(
            request,
            'Only cancelled appointments can be deleted.',
        )
        return redirect('appointments:admin_list')

    owner_email = (
        appointment.user.email
        if appointment.user and appointment.user.email
        else appointment.owner_email
    )
    if not owner_email:
        messages.error(
            request,
            'Add a customer email before deleting this appointment so the customer can be notified.',
        )
        return redirect('appointments:admin_list')

    from notifications.email_utils import send_appointment_deletion_email
    if not send_appointment_deletion_email(appointment):
        messages.error(
            request,
            'The customer could not be notified by email, so the appointment was not deleted.',
        )
        return redirect('appointments:admin_list')

    if appointment.user_id:
        create_notification(
            user=appointment.user,
            title=f'Cancelled appointment record removed for {appointment.pet_name}',
            message=(
                f'The cancelled appointment for {appointment.pet_name} on '
                f'{appointment.appointment_date:%B %d, %Y} at '
                f'{appointment.appointment_time:%I:%M %p} was removed from '
                'the clinic system by staff. The cancellation remains final.'
            ),
            notification_type=Notification.NotificationType.APPOINTMENT_CANCELLED,
            module_context=Notification.ModuleContext.APPOINTMENTS,
        )

    name = appointment.pet_name
    appointment.delete()
    messages.success(
        request,
        f'Cancelled appointment for {name} was deleted after notifying the customer.',
    )
    return redirect('appointments:admin_list')


@login_required
@module_permission_required('appointments', 'VIEW')
def api_pet_owners(request):
    """API: return list of registered pet owners for admin dropdown."""
    # Include new accounts before they have registered a pet profile.
    owners = User.objects.filter(
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
def api_walkin_guests(request):
    """API: search existing walk-in/guest appointment records by owner name, phone, or pet name.
    
    Searches two sources:
    1. Appointment records with source=WALKIN (owner_name, owner_phone, pet_name)
    2. Pet model records with source=WALKIN (guest_owner_name, guest_owner_phone, name)
    """
    q = request.GET.get('q', '').strip()
    if not q or len(q) < 2:
        return JsonResponse({'guests': []})

    # ── Source 1: Walk-in appointment history ──
    guests_qs = Appointment.objects.filter(
        source=Appointment.Source.WALKIN,
    ).filter(
        Q(owner_name__icontains=q) |
        Q(owner_phone__icontains=q) |
        Q(pet_name__icontains=q)
    ).values(
        'owner_name', 'owner_phone', 'owner_email', 'owner_address', 'pet_name'
    ).distinct().order_by('owner_name')[:40]

    # Deduplicate by name+phone combination and aggregate pet names
    seen = {}
    for g in guests_qs:
        owner_name_safe = (g['owner_name'] or '').strip()
        owner_phone_safe = (g['owner_phone'] or '').strip()

        key = (owner_name_safe.lower(), owner_phone_safe.lower())
        if key not in seen:
            seen[key] = {
                'name': owner_name_safe or 'Unknown',
                'phone': owner_phone_safe,
                'email': (g['owner_email'] or '').strip(),
                'address': (g['owner_address'] or '').strip(),
                'pets': []
            }

        pet = (g.get('pet_name') or '').strip()
        if pet and pet not in seen[key]['pets']:
            seen[key]['pets'].append(pet)

    # ── Source 2: Patient records with walk-in source (guest_owner fields) ──
    from patients.models import Pet as PetModel
    walkin_pets_qs = PetModel.objects.filter(
        source=PetModel.Source.WALKIN,
    ).filter(
        Q(guest_owner_name__icontains=q) |
        Q(guest_owner_phone__icontains=q) |
        Q(name__icontains=q)
    ).values(
        'guest_owner_name', 'guest_owner_phone', 'guest_owner_email', 'guest_owner_address', 'name'
    ).order_by('guest_owner_name')[:40]

    for p in walkin_pets_qs:
        owner_name_safe = (p['guest_owner_name'] or '').strip()
        owner_phone_safe = (p['guest_owner_phone'] or '').strip()

        key = (owner_name_safe.lower(), owner_phone_safe.lower())
        if key not in seen:
            seen[key] = {
                'name': owner_name_safe or 'Unknown',
                'phone': owner_phone_safe,
                'email': (p['guest_owner_email'] or '').strip(),
                'address': (p['guest_owner_address'] or '').strip(),
                'pets': []
            }

        pet = (p.get('name') or '').strip()
        if pet and pet not in seen[key]['pets']:
            seen[key]['pets'].append(pet)

    guests = list(seen.values())[:20]
    return JsonResponse({'guests': guests})


@login_required
@module_permission_required('appointments', 'VIEW')
def api_walkin_guest_pets(request):
    """API: return pets for a walk-in guest owner, searched by name and/or phone.

    Combines results from:
    1. Pet model — guest_owner_name / guest_owner_phone fields (registered walk-in patients)
    2. Appointment model — owner_name / owner_phone fields (walk-in appointment history)
    """
    from patients.models import Pet as PetModel
    name = request.GET.get('name', '').strip()
    phone = request.GET.get('phone', '').strip()

    if not name and not phone:
        return JsonResponse({'pets': []})

    pets = []
    seen = set()  # (name_lower, species_lower) dedup key

    # ── Source 1: Pet model (registered walk-in patients) ──
    pet_filter = Q()
    if name:
        pet_filter |= Q(guest_owner_name__iexact=name)
    if phone:
        pet_filter |= Q(guest_owner_phone=phone)

    for pet in PetModel.objects.filter(pet_filter, source=PetModel.Source.WALKIN).order_by('name'):
        key = (pet.name.lower(), (pet.species or '').lower())
        if key not in seen:
            seen.add(key)
            pets.append({
                'id': pet.id,
                'name': pet.name,
                'species': pet.species or '',
                'breed': pet.breed or '',
                'dob': pet.date_of_birth.isoformat() if pet.date_of_birth else '',
                'sex': pet.sex or '',
                'color': pet.color or '',
                'source': 'patient',
            })

    # ── Source 2: Appointment history (walk-in appointments with pet info) ──
    appt_filter = Q(source=Appointment.Source.WALKIN)
    if name:
        appt_filter &= Q(owner_name__iexact=name)
    if phone:
        appt_filter |= Q(source=Appointment.Source.WALKIN, owner_phone=phone)

    appt_pets = Appointment.objects.filter(appt_filter).exclude(
        pet_name=''
    ).values(
        'pet_name', 'pet_species', 'pet_breed', 'pet_dob', 'pet_sex', 'pet_color'
    ).distinct().order_by('pet_name')

    for ap in appt_pets:
        key = ((ap['pet_name'] or '').lower(), (ap['pet_species'] or '').lower())
        if key not in seen:
            seen.add(key)
            pets.append({
                'id': None,
                'name': ap['pet_name'] or '',
                'species': ap['pet_species'] or '',
                'breed': ap['pet_breed'] or '',
                'dob': ap['pet_dob'] or '',
                'sex': ap['pet_sex'] or '',
                'color': ap['pet_color'] or '',
                'source': 'appointment',
            })

    return JsonResponse({'pets': pets})


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
