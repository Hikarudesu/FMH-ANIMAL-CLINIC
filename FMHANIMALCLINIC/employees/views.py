from datetime import date, timedelta
import calendar

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.db.models import Q

from accounts.decorators import module_permission_required, special_permission_required, admin_only
from accounts.rbac_models import Role
from branches.models import Branch
from employees.models import StaffMember, VetSchedule, RecurringSchedule, SCHEDULE_LOOKAHEAD_DAYS
from employees.forms import StaffMemberForm, VetScheduleForm, RecurringScheduleForm
from settings.models import get_shift_type_choices


# ──────────────────────── STAFF MANAGEMENT ────────────────────────

@login_required
@module_permission_required('staff', 'VIEW')
def staff_list(request):
    """List all staff members - shows users with staff roles assigned via RBAC."""
    from accounts.models import User

    q = request.GET.get('q', '').strip()
    branch_id = request.GET.get('branch', '')
    position = request.GET.get('position', '')

    # Get all users with staff roles assigned, excluding superadmin (owner)
    staff_users = User.objects.filter(
        assigned_role__is_staff_role=True
    ).exclude(
        assigned_role__code='superadmin'
    ).select_related('assigned_role', 'branch', 'staff_profile')

    # Apply search filter
    if q:
        staff_users = staff_users.filter(
            Q(first_name__icontains=q) |
            Q(last_name__icontains=q) |
            Q(email__icontains=q) |
            Q(username__icontains=q)
        )

    # Apply branch filter
    if branch_id:
        staff_users = staff_users.filter(branch_id=branch_id)

    # Apply role filter from dropdown (labeled as "Position" in UI)
    if position:
        try:
            staff_users = staff_users.filter(assigned_role_id=int(position))
        except (TypeError, ValueError):
            pass

    # Build dropdown options from live RBAC roles (Roles & Permissions)
    role_positions = list(
        Role.objects.filter(is_staff_role=True)
        .exclude(code__in=['superadmin', 'user'])
        .order_by('-hierarchy_level', 'name')
        .values_list('id', 'name')
    )
    positions = [(str(role_id), role_name) for role_id, role_name in role_positions]

    branches = Branch.objects.filter(is_active=True)

    return render(request, 'employees/staff_list.html', {
        'staff_users': staff_users,
        'branches': branches,
        'positions': positions,
        'q': q,
        'selected_branch': branch_id,
        'selected_position': position,
    })


@login_required
@module_permission_required('staff', 'CREATE')
def staff_add(request):
    """Add a new staff member."""
    if request.method == 'POST':
        form = StaffMemberForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Staff member added successfully.')
            return redirect('employees:staff_list')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = StaffMemberForm()

    return render(request, 'employees/staff_form.html', {
        'form': form,
        'action': 'Add',
    })


@login_required
@module_permission_required('staff', 'EDIT')
def staff_edit(request, user_id):
    """Edit staff member profile (salary, license, etc.) via their user account."""
    from accounts.models import User

    user = get_object_or_404(User, pk=user_id, assigned_role__is_staff_role=True)

    # Get or create StaffMember profile
    staff_profile, created = StaffMember.objects.get_or_create(
        user=user,
        defaults={
            'first_name': user.first_name,
            'last_name': user.last_name,
            'email': user.email,
            'phone': user.phone_number or '',
            'branch': user.branch,
            'position': StaffMember.Position.RECEPTIONIST,  # Default
            'is_active': True,
        }
    )

    # Always sync branch from User account (in case it was changed via Assign Roles)
    if not created:
        staff_profile.branch = user.branch
        staff_profile.save(update_fields=['branch'])

    if request.method == 'POST':
        branch_id = request.POST.get('branch', '').strip()
        is_active = request.POST.get('is_active') == 'on'
        branch = None
        if branch_id:
            branch = Branch.objects.filter(pk=branch_id).first()
            if not branch:
                messages.error(request, 'Please choose a valid branch.')
                return render(request, 'employees/staff_edit.html', {
                    'edited_user': user,
                    'staff_profile': staff_profile,
                    'branches': Branch.objects.filter(is_active=True),
                })

        user.branch = branch
        user.save(update_fields=['branch'])

        staff_profile.branch = branch
        staff_profile.is_active = is_active
        staff_profile.save(update_fields=['branch', 'is_active'])

        messages.success(request, f'{user.get_full_name()} profile updated successfully.')
        return redirect('employees:staff_list')

    return render(request, 'employees/staff_edit.html', {
        'edited_user': user,
        'staff_profile': staff_profile,
        'branches': Branch.objects.filter(is_active=True),
    })


@login_required
@module_permission_required('staff', 'DELETE')
def staff_delete(request, pk):
    """Soft-delete a staff member — deactivate and optionally reassign appointments."""
    member = get_object_or_404(StaffMember, pk=pk)

    # Get future appointments assigned to this vet
    from appointments.models import Appointment
    future_appointments = Appointment.objects.filter(
        preferred_vet=member,
        appointment_date__gte=date.today(),
    ).exclude(status__in=['CANCELLED', 'COMPLETED'])

    # Get available vets for reassignment (same branch, excluding current)
    reassign_vets = StaffMember.objects.filter(
        position=StaffMember.Position.VETERINARIAN,
        is_active=True,
        branch=member.branch,
    ).exclude(pk=pk) if member.is_vet else StaffMember.objects.none()

    if request.method == 'POST':
        action = request.POST.get('action', 'deactivate')
        reassign_to_id = request.POST.get('reassign_to', '')

        if action == 'deactivate':
            # Reassign appointments if a vet was selected
            if reassign_to_id and future_appointments.exists():
                reassign_vet = get_object_or_404(
                    StaffMember, pk=reassign_to_id)
                count = future_appointments.update(preferred_vet=reassign_vet)
                messages.info(
                    request, f'{count} appointment(s) reassigned to {reassign_vet.full_name}.')
            elif future_appointments.exists():
                # No reassignment — set preferred_vet to None
                future_appointments.update(preferred_vet=None)
                messages.info(
                    request, f'{future_appointments.count()} appointment(s) set to "Any available vet".')

            # Soft-delete: deactivate instead of hard delete
            member.is_active = False
            member.save(update_fields=['is_active'])
            messages.success(
                request, f'{member.full_name} has been deactivated.')
        else:
            # Hard delete (only if user explicitly chose)
            name = member.full_name
            member.delete()
            messages.success(request, f'{name} has been permanently removed.')

        return redirect('employees:staff_list')

    return render(request, 'employees/staff_delete.html', {
        'member': member,
        'future_appointments': future_appointments,
        'reassign_vets': reassign_vets,
    })


# ──────────────────────── SCHEDULE CALENDAR ────────────────────────


def _can_manage_other_schedules(user):
    return user.can_manage_other_schedules()


def _can_manage_own_schedule(user):
    return user.has_special_permission('can_manage_own_schedule')


def _can_manage_any_schedule(user):
    return _can_manage_other_schedules(user) or _can_manage_own_schedule(user)


def _get_schedule_permissions(user):
    """
    Get detailed schedule permissions for a user.
    
    Returns:
        dict: {
            'can_manage_others': bool,
            'can_manage_own': bool,
            'can_add_own': bool,  # Can add their own schedule
            'can_see_others': bool,  # Can see others' schedules
            'is_admin': bool,  # Can choose any staff in forms
        }
    """
    can_manage_others = _can_manage_other_schedules(user)
    can_manage_own = _can_manage_own_schedule(user)
    
    return {
        'can_manage_others': can_manage_others,
        'can_manage_own': can_manage_own,
        'can_add_own': can_manage_own,  # If they have manage_own, they can add their own
        'can_see_others': can_manage_others,  # If they have manage_others, they can see others
        'is_admin': can_manage_others,  # Only others-managers can choose any staff
    }


@login_required
@special_permission_required(('can_manage_own_schedule', 'can_manage_others_schedule'))
def schedule_view(request):
    """Schedule calendar page."""
    user = request.user
    perms = _get_schedule_permissions(user)
    branches = Branch.objects.filter(is_active=True)
    form = VetScheduleForm(is_admin=perms['is_admin'], user=user)
    recurring_form = RecurringScheduleForm(is_admin=perms['is_admin'], user=user)

    can_manage_any_schedule = _can_manage_any_schedule(user)
    can_clear_all = user.is_superuser or (user.assigned_role and user.assigned_role.hierarchy_level >= 10)

    # Get the user's staff profile for non-admins
    user_staff = None
    user_branch = getattr(user, 'branch', None)
    
    if not perms['can_see_others']:
        try:
            user_staff = user.staff_profile
        except StaffMember.DoesNotExist:
            pass

    # Filter recurring schedules based on permissions
    if perms['can_see_others']:
        recurring_schedules = RecurringSchedule.objects.filter(
            is_active=True
        ).select_related('staff', 'branch')
    else:
        recurring_schedules = RecurringSchedule.objects.filter(
            is_active=True,
            staff=user_staff
        ).select_related('staff', 'branch') if user_staff else RecurringSchedule.objects.none()
        # Non-admins only see their assigned branch
        if user_branch:
            branches = branches.filter(pk=user_branch.pk)

    # Group recurring schedules by their common attributes (staff, branch, times, shift_type)
    grouped_recurring = {}
    for rs in recurring_schedules:
        key = (rs.staff_id, rs.branch_id, rs.start_time, rs.end_time, rs.shift_type)
        if key not in grouped_recurring:
            grouped_recurring[key] = {
                'staff': rs.staff,
                'branch': rs.branch,
                'start_time': rs.start_time,
                'end_time': rs.end_time,
                'shift_type': rs.shift_type,
                'shift_type_display': rs.get_shift_type_display(),
                'days': [],
                'sample_rs': rs  # For delete URL
            }
        grouped_recurring[key]['days'].append(rs.day_of_week)

    # Sort days and convert to display names
    for group in grouped_recurring.values():
        group['days'].sort()
        group['days_display'] = [RecurringSchedule.DayOfWeek(day).label for day in group['days']]

    return render(request, 'employees/schedule.html', {
        'branches': branches,
        'form': form,
        'recurring_form': recurring_form,
        'recurring_schedules': list(grouped_recurring.values()),
        'shift_types': get_shift_type_choices(),
        'can_manage_schedule': can_manage_any_schedule,
        'can_manage_other_schedules': perms['can_manage_others'],
        'can_clear_all': can_clear_all,
        'user_staff': user_staff,
        'user_branch': user_branch,
    })


@login_required
@special_permission_required(('can_manage_own_schedule', 'can_manage_others_schedule'))
def schedule_api(request):
    """JSON API — returns schedule entries for a given month/branch."""
    user = request.user
    perms = _get_schedule_permissions(user)
    user_branch = getattr(user, 'branch', None)
    
    try:
        year = int(request.GET.get('year', date.today().year))
    except (ValueError, TypeError):
        year = date.today().year
    try:
        month = int(request.GET.get('month', date.today().month))
    except (ValueError, TypeError):
        month = date.today().month
    branch_id = request.GET.get('branch', '')

    # Get first and last day of month
    _, last_day = calendar.monthrange(year, month)
    start = date(year, month, 1)
    end = date(year, month, last_day)

    schedules = VetSchedule.objects.filter(
        date__gte=start,
        date__lte=end,
    ).select_related('staff', 'branch')

    # Filter schedules based on permissions
    if perms['can_see_others']:
        if branch_id and branch_id != '':
            schedules = schedules.filter(branch_id=branch_id)
    else:
        try:
            user_staff = user.staff_profile
        except StaffMember.DoesNotExist:
            return JsonResponse({'events': [], 'year': year, 'month': month})

        schedules = schedules.filter(staff=user_staff)
        if user_branch:
            schedules = schedules.filter(branch=user_branch)

    events = []
    user_staff = None

    # Get current user's staff profile for ownership checks
    if perms['can_manage_own'] or not perms['can_see_others']:
        try:
            user_staff = user.staff_profile
        except StaffMember.DoesNotExist:
            pass

    for s in schedules:
        # Check if user can edit/delete this schedule
        can_edit = perms['can_manage_others'] or (user_staff and s.staff == user_staff)

        events.append({
            'id': s.id,
            'staffName': s.staff.full_name,
            'staffId': s.staff.id,
            'staffPosition': s.staff.get_position_display(),
            'date': s.date.isoformat(),
            'startTime': s.start_time.strftime('%H:%M'),
            'endTime': s.end_time.strftime('%H:%M'),
            'branch': s.branch.name if s.branch else '',
            'isAvailable': s.is_available,
            'shiftType': s.shift_type,
            'shiftTypeDisplay': s.get_shift_type_display(),
            'notes': s.notes,
            'canEdit': can_edit,  # Add permission flag
        })

    return JsonResponse({'events': events, 'year': year, 'month': month})


@login_required
@special_permission_required(('can_manage_own_schedule', 'can_manage_others_schedule'))
def available_staff_api(request):
    """JSON API — returns available vets/vet assistants for a given branch."""
    user = request.user
    perms = _get_schedule_permissions(user)
    branch_id = request.GET.get('branch_id', '')
    user_branch = getattr(user, 'branch', None)

    if perms['is_admin']:
        if not branch_id:
            return JsonResponse({'staff': []})

        # Get vets and vet assistants for the selected branch
        staff = StaffMember.objects.schedulable_staff(branch_id=branch_id)
    else:
        try:
            user_staff = user.staff_profile
        except StaffMember.DoesNotExist:
            return JsonResponse({'staff': []})

        if branch_id and str(user_staff.branch_id or '') != str(branch_id):
            return JsonResponse({'staff': []})

        staff = StaffMember.objects.filter(
            pk=user_staff.pk,
            is_active=True,
        ).select_related('user', 'user__assigned_role')

    staff_list = []
    for member in staff:
        staff_list.append({
            'id': member.id,
            'name': member.full_name,
            'position': member.user.assigned_role.name if member.user and member.user.assigned_role else 'Staff',
        })

    return JsonResponse({'staff': staff_list})


@login_required
@special_permission_required(('can_manage_own_schedule', 'can_manage_others_schedule'))
def schedule_add(request):
    """Add a schedule entry or recurring template (POST only)."""
    if request.method == 'POST':
        is_recurring = request.POST.get('is_recurring') == 'on'
        user = request.user

        perms = _get_schedule_permissions(user)

        # Get the user's staff profile
        user_staff = None
        user_branch = None
        try:
            user_staff = user.staff_profile
            user_branch = user.branch
        except StaffMember.DoesNotExist:
            if perms['can_add_own']:
                messages.error(request, 'You do not have a staff profile. Contact an administrator.')
                return redirect('employees:schedule')

        if is_recurring:
            form = RecurringScheduleForm(request.POST, is_admin=perms['is_admin'], user=user)
            if form.is_valid():
                selected_staff = form.cleaned_data['staff']
                
                # Permission checks
                if perms['is_admin']:
                    # Can choose any staff
                    staff = selected_staff
                    branch = form.cleaned_data['branch']
                elif perms['can_add_own'] and perms['can_manage_others']:
                    # Can choose any staff including own
                    staff = selected_staff
                    branch = form.cleaned_data['branch']
                elif perms['can_manage_others'] and not perms['can_add_own']:
                    # Can manage others but not add own - prevent selecting self
                    if selected_staff == user_staff:
                        messages.error(request, 'You cannot add schedules for yourself. You can only manage others\' schedules.')
                        return redirect('employees:schedule')
                    staff = selected_staff
                    branch = form.cleaned_data['branch']
                elif perms['can_add_own']:
                    # Can only add own schedule
                    staff = user_staff
                    branch = user_branch
                else:
                    messages.error(request, 'You do not have permission to add schedules.')
                    return redirect('employees:schedule')

                selected_days = form.cleaned_data['days_of_week']
                created_entries = []

                for day in selected_days:
                    entry = RecurringSchedule(
                        staff=staff,
                        branch=branch,
                        day_of_week=int(day),
                        start_time=form.cleaned_data['start_time'],
                        end_time=form.cleaned_data['end_time'],
                        shift_type=form.cleaned_data.get(
                            'shift_type', 'GENERAL'),
                        is_active=True,
                        effective_from=form.cleaned_data.get('effective_from'),
                        effective_until=form.cleaned_data.get(
                            'effective_until'),
                    )
                    entry.save()  # triggers auto-generation via save() override
                    created_entries.append(entry.get_day_of_week_display())

                day_names = ', '.join(created_entries)
                messages.success(
                    request,
                    f'Recurring template(s) added for {staff.full_name} '
                    f'on {day_names}. Auto-generated schedule entries for the next 30 days.'
                )
            else:
                error_details = '; '.join(
                    f'{field}: {", ".join(errs)}' for field, errs in form.errors.items()
                )
                messages.error(
                    request, f'Could not add recurring template — {error_details}')
        else:
            form = VetScheduleForm(request.POST, is_admin=perms['is_admin'], user=user)
            if form.is_valid():
                schedule = form.save(commit=False)
                
                # Permission checks
                if perms['is_admin']:
                    # Can choose any staff
                    pass  # Use form data as-is
                elif perms['can_add_own'] and perms['can_manage_others']:
                    # Can choose any staff including own
                    pass  # Use form data as-is
                elif perms['can_manage_others'] and not perms['can_add_own']:
                    # Can manage others but not add own - prevent selecting self
                    if schedule.staff == user_staff:
                        messages.error(request, 'You cannot add schedules for yourself. You can only manage others\' schedules.')
                        return redirect('employees:schedule')
                elif perms['can_add_own']:
                    # Can only add own schedule
                    schedule.staff = user_staff
                    schedule.branch = user_branch
                else:
                    messages.error(request, 'You do not have permission to add schedules.')
                    return redirect('employees:schedule')
                    
                schedule.save()
                messages.success(request, 'Schedule entry added.')
            else:
                error_details = '; '.join(
                    f'{field}: {", ".join(errs)}' for field, errs in form.errors.items()
                )
                messages.error(
                    request, f'Invalid schedule data. Please check the form. {error_details}')
    return redirect('employees:schedule')


@login_required
@special_permission_required(('can_manage_own_schedule', 'can_manage_others_schedule'))
def schedule_edit(request, pk):
    """Edit an existing schedule entry."""
    entry = get_object_or_404(VetSchedule, pk=pk)
    user = request.user

    perms = _get_schedule_permissions(user)

    # Check if user can edit this entry
    can_edit_this = perms['can_manage_others'] or (perms['can_manage_own'] and entry.staff == user.staff_profile)
    
    if not can_edit_this:
        messages.error(request, 'You do not have permission to edit this schedule entry.')
        return redirect('employees:schedule')

    if request.method == 'POST':
        entry.is_available = request.POST.get('is_available') == 'on'
        entry.shift_type = request.POST.get('shift_type', entry.shift_type)
        entry.notes = request.POST.get('notes', entry.notes)

        start_time = request.POST.get('start_time')
        end_time = request.POST.get('end_time')
        if start_time:
            entry.start_time = start_time
        if end_time:
            entry.end_time = end_time

        entry.save()
        messages.success(request, 'Schedule entry updated.')
    return redirect('employees:schedule')


@login_required
@special_permission_required(('can_manage_own_schedule', 'can_manage_others_schedule'))
def schedule_delete(request, pk):
    """Delete a schedule entry."""
    entry = get_object_or_404(VetSchedule, pk=pk)
    user = request.user

    perms = _get_schedule_permissions(user)

    # Check if user can delete this entry
    can_delete_this = perms['can_manage_others'] or (perms['can_manage_own'] and entry.staff == user.staff_profile)
    
    if not can_delete_this:
        messages.error(request, 'You do not have permission to delete this schedule entry.')
        return redirect('employees:schedule')

    if request.method == 'POST':
        entry.delete()
        messages.success(request, 'Schedule entry removed.')
    return redirect('employees:schedule')


@login_required
@special_permission_required(('can_manage_own_schedule', 'can_manage_others_schedule'))
def schedule_clear_all(request):
    """Delete ALL schedule entries the user can manage."""
    if request.method == 'POST':
        user = request.user
        perms = _get_schedule_permissions(user)

        if perms['can_manage_others']:
            qs = VetSchedule.objects.all()
        else:
            try:
                user_staff = user.staff_profile
                qs = VetSchedule.objects.filter(staff=user_staff)
            except StaffMember.DoesNotExist:
                messages.error(request, 'Unable to clear schedules: no staff profile found.')
                return redirect('employees:schedule')

        count = qs.count()
        if count > 0:
            qs.delete()
            messages.success(
                request, f'All {count} schedule entries have been deleted.')
        else:
            messages.info(request, 'No schedule entries to delete.')
    return redirect('employees:schedule')


@login_required
@special_permission_required(('can_manage_own_schedule', 'can_manage_others_schedule'))
def recurring_clear_all(request):
    """Delete ALL recurring schedule templates the user can manage, and their generated schedules."""
    user = request.user
    perms = _get_schedule_permissions(user)

    if request.method == 'POST':
        if perms['can_manage_others']:
            templates_qs = RecurringSchedule.objects.filter(is_active=True)
        else:
            try:
                user_staff = user.staff_profile
                templates_qs = RecurringSchedule.objects.filter(
                    is_active=True, staff=user_staff)
            except StaffMember.DoesNotExist:
                templates_qs = RecurringSchedule.objects.none()

        # Delete generated schedules for these templates
        generated_to_delete = VetSchedule.objects.none()
        for template in templates_qs:
            django_week_day = ((template.day_of_week + 1) % 7) + 1
            generated_to_delete |= VetSchedule.objects.filter(
                staff=template.staff,
                branch=template.branch,
                start_time=template.start_time,
                end_time=template.end_time,
                date__week_day=django_week_day,
            )

        generated_count = generated_to_delete.distinct().count()
        generated_to_delete.delete()

        template_count = templates_qs.count()
        templates_qs.delete()

        messages.success(
            request, f'All {template_count} recurring schedule templates and {generated_count} generated schedule entries have been deleted.')
    return redirect('employees:schedule')


# ──────────────────────── RECURRING SCHEDULES ────────────────────────

@login_required
@special_permission_required(('can_manage_own_schedule', 'can_manage_others_schedule'))
def recurring_list(request):
    """JSON API — returns all active recurring schedules."""
    user = request.user
    perms = _get_schedule_permissions(user)
    
    schedules = RecurringSchedule.objects.filter(
        is_active=True
    ).select_related('staff', 'branch')
    
    # Filter based on permissions
    if not perms['can_see_others']:
        try:
            user_staff = user.staff_profile
            schedules = schedules.filter(staff=user_staff)
        except StaffMember.DoesNotExist:
            schedules = RecurringSchedule.objects.none()

    data = []
    for rs in schedules:
        data.append({
            'id': rs.id,
            'staffName': rs.staff.full_name,
            'branch': rs.branch.name,
            'dayOfWeek': rs.get_day_of_week_display(),
            'startTime': rs.start_time.strftime('%H:%M'),
            'endTime': rs.end_time.strftime('%H:%M'),
            'shiftType': rs.get_shift_type_display(),
        })
    return JsonResponse({'schedules': data})


@login_required
@special_permission_required(('can_manage_own_schedule', 'can_manage_others_schedule'))
def recurring_add(request):
    """Add recurring schedule templates — supports multiple days at once."""
    if request.method == 'POST':
        user = request.user
        perms = _get_schedule_permissions(user)
        
        # Get the user's staff profile
        user_staff = None
        user_branch = None
        try:
            user_staff = user.staff_profile
            user_branch = user.branch
        except StaffMember.DoesNotExist:
            if perms['can_add_own']:
                messages.error(request, 'You do not have a staff profile. Contact an administrator.')
                return redirect('employees:schedule')
        
        form = RecurringScheduleForm(request.POST, is_admin=perms['is_admin'])
        if form.is_valid():
            selected_staff = form.cleaned_data['staff']
            
            # Permission checks
            if perms['is_admin']:
                # Can choose any staff
                staff = selected_staff
                branch = form.cleaned_data['branch']
            elif perms['can_add_own'] and perms['can_manage_others']:
                # Can choose any staff including own
                staff = selected_staff
                branch = form.cleaned_data['branch']
            elif perms['can_manage_others'] and not perms['can_add_own']:
                # Can manage others but not add own - prevent selecting self
                if selected_staff == user_staff:
                    messages.error(request, 'You cannot add recurring schedules for yourself. You can only manage others\' schedules.')
                    return redirect('employees:schedule')
                staff = selected_staff
                branch = form.cleaned_data['branch']
            elif perms['can_add_own']:
                # Can only add own schedule
                staff = user_staff
                branch = user_branch
            else:
                messages.error(request, 'You do not have permission to add recurring schedules.')
                return redirect('employees:schedule')

            # list of day ints
            selected_days = form.cleaned_data['days_of_week']
            created_entries = []

            for day in selected_days:
                entry = RecurringSchedule(
                    staff=staff,
                    branch=branch,
                    day_of_week=int(day),
                    start_time=form.cleaned_data['start_time'],
                    end_time=form.cleaned_data['end_time'],
                    shift_type=form.cleaned_data.get('shift_type', 'GENERAL'),
                    is_active=True,
                    effective_from=form.cleaned_data.get('effective_from'),
                    effective_until=form.cleaned_data.get('effective_until'),
                )
                entry.save()  # triggers auto-generation via save() override
                created_entries.append(entry.get_day_of_week_display())

            day_names = ', '.join(created_entries)
            messages.success(
                request,
                f'Recurring template(s) added for {staff.full_name} '
                f'on {day_names}. Auto-generated schedule entries for the next 30 days.'
            )
        else:
            error_details = '; '.join(
                f'{field}: {", ".join(errs)}' for field, errs in form.errors.items()
            )
            messages.error(
                request, f'Could not add recurring template — {error_details}')
    return redirect('employees:schedule')


@login_required
@special_permission_required(('can_manage_own_schedule', 'can_manage_others_schedule'))
def recurring_delete(request, pk):
    """Delete a recurring schedule template."""
    entry = get_object_or_404(RecurringSchedule, pk=pk)
    user = request.user

    perms = _get_schedule_permissions(user)

    # Check if user can delete this entry
    can_delete_this = perms['can_manage_others'] or (perms['can_manage_own'] and entry.staff == user.staff_profile)
    
    if not can_delete_this:
        messages.error(request, 'You do not have permission to delete this recurring schedule template.')
        return redirect('employees:schedule')

    if request.method == 'POST':
        # Delete the entire set of recurring templates with matching attributes
        entry_set = RecurringSchedule.objects.filter(
            staff=entry.staff,
            branch=entry.branch,
            start_time=entry.start_time,
            end_time=entry.end_time,
            shift_type=entry.shift_type,
            is_active=True
        )

        # Also delete generated VetSchedule entries for the current week for all in the set
        today = date.today()
        week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=6)

        generated_schedules = VetSchedule.objects.filter(
            staff=entry.staff,
            branch=entry.branch,
            start_time=entry.start_time,
            end_time=entry.end_time,
            date__gte=week_start,
            date__lte=week_end,
        ).filter(date__week_day__in=[((rs.day_of_week + 1) % 7) + 1 for rs in entry_set])

        deleted_count = generated_schedules.count()
        generated_schedules.delete()
        entry_set.delete()

        messages.success(
            request,
            f'Deleted {deleted_count} generated schedule entr{ "y" if deleted_count == 1 else "ies" } for the week of {week_start.strftime("%b %d, %Y")}. The recurring template set has been removed.'
        )

        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': True,
                'message': 'Recurring template removed.',
                'deleted_count': deleted_count,
                'recurring_id': pk,
            })
    return redirect('employees:schedule')


# ──────────────────────── PAYSLIP GENERATION ────────────────────────

@login_required
@module_permission_required('payroll', 'VIEW')
def payslip_list_view(request):
    """Admin view: list all staff members to generate payslips."""
    # Default to current month/year
    today = date.today()
    try:
        month = int(request.GET.get('month', today.month))
    except (ValueError, TypeError):
        month = today.month
    try:
        year = int(request.GET.get('year', today.year))
    except (ValueError, TypeError):
        year = today.year

    # Generate list of months for the dropdown
    months = [{'num': i, 'name': date(2000, i, 1).strftime('%B')}
              for i in range(1, 13)]

    staff = StaffMember.objects.filter(
        is_active=True,
        user__isnull=False,
        user__assigned_role__is_staff_role=True
    ).order_by('last_name', 'first_name')

    return render(request, 'employees/payslip_list.html', {
        'staff_list': staff,
        'selected_month': month,
        'selected_year': year,
        'months': months,
    })


@login_required
@module_permission_required('payroll', 'VIEW')
def payslip_detail_view(request, pk):
    """Admin view: generate and display a specific payslip."""
    from employees.payslip_utils import compute_payslip

    staff_member = get_object_or_404(StaffMember, pk=pk)

    today = date.today()
    try:
        month = int(request.GET.get('month', today.month))
    except (ValueError, TypeError):
        month = today.month
    try:
        year = int(request.GET.get('year', today.year))
    except (ValueError, TypeError):
        year = today.year

    # Compute the payslip data
    payslip_data = compute_payslip(staff_member, month, year)

    return render(request, 'employees/payslip.html', {
        'payslip': payslip_data,
        'month': month,
        'year': year,
    })
