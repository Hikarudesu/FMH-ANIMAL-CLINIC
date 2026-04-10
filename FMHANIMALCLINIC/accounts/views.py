"""Views for the accounts app."""
# pylint: disable=no-member,import-outside-toplevel

import json
from decimal import Decimal
from datetime import date, timedelta
from django.db.models import Count, Sum, Q, F
from django.db.models.functions import TruncDate
from django.core.serializers.json import DjangoJSONEncoder

from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator

from branches.models import Branch
from .models import User
from .decorators import module_permission_required, admin_only, special_permission_required, staff_only
from .forms import PetOwnerRegistrationForm


def get_month_offset(base_date, months_back):
    """Calculate date offset by months without external dependencies."""
    year = base_date.year
    month = base_date.month - months_back
    while month <= 0:
        month += 12
        year -= 1
    return date(year, month, 1)


def login_view(request):
    """Login page — redirects to correct portal after login."""
    next_url = request.GET.get('next') or request.POST.get('next')

    if request.user.is_authenticated:
        if next_url:
            return redirect(next_url)
        if request.user.is_clinic_staff():
            # Redirect based on specific role
            if request.user.assigned_role and request.user.assigned_role.code == 'veterinarian':
                return redirect('vet_dashboard')
            elif request.user.assigned_role and request.user.assigned_role.code == 'vet_assistant':
                return redirect('vet_dashboard')  # Vet assistants share the vet dashboard
            elif request.user.assigned_role and request.user.assigned_role.code == 'receptionist':
                return redirect('receptionist_dashboard')
            else:
                return redirect('admin_dashboard')
        return redirect('user_dashboard')

    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            messages.success(request, 'Successfully logged in.')

            if next_url:
                return redirect(next_url)
            if user.is_clinic_staff():
                # Redirect based on specific role
                if user.assigned_role and user.assigned_role.code == 'veterinarian':
                    return redirect('vet_dashboard')
                elif user.assigned_role and user.assigned_role.code == 'vet_assistant':
                    return redirect('vet_dashboard')  # Vet assistants share the vet dashboard
                elif user.assigned_role and user.assigned_role.code == 'receptionist':
                    return redirect('receptionist_dashboard')
                else:
                    return redirect('admin_dashboard')
            return redirect('user_dashboard')
        else:
            messages.error(request, 'Invalid username or password')

    return render(request, 'accounts/login.html')


def register_view(request):
    """Register page view for Pet Owner registration"""
    if request.method == 'POST':
        form = PetOwnerRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            # Auto-login after registration
            login(request, user)
            messages.success(request, 'Account created successfully!')
            return redirect('select_branch')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = PetOwnerRegistrationForm()

    return render(request, 'accounts/register.html', {'form': form})


@login_required
def select_branch_view(request):
    """Branch selection page — shown after pet owner registration."""
    branches = Branch.objects.filter(is_active=True)

    if request.method == 'POST':
        branch_id = request.POST.get('branch_id')
        if branch_id:
            branch = get_object_or_404(Branch, id=branch_id, is_active=True)
            request.user.branch = branch
            request.user.save(update_fields=['branch'])
            messages.success(
                request, f'Welcome! You are now registered at {branch.name}.')
        return redirect('user_dashboard')

    return render(request, 'accounts/select_branch.html', {'branches': branches})


def logout_view(request):
    """Logout view"""
    logout(request)
    messages.success(request, 'You have been successfully logged out.')
    return redirect('landing_page')


@login_required
def delete_activity_view(request, activity_id):
    """Delete a specific activity."""
    if request.method == 'POST':
        from accounts.models import UserActivity
        activity = get_object_or_404(UserActivity, id=activity_id, user=request.user)
        activity.delete()
        messages.success(request, 'Activity deleted successfully.')
    return redirect(f"{reverse('accounts:user_dashboard')}#dashboard-activity-section")

@login_required
def clear_all_activities_view(request):
    """Clear all activities for the current user."""
    if request.method == 'POST':
        from accounts.models import UserActivity
        UserActivity.objects.filter(user=request.user).delete()
        messages.success(request, 'All recent activities have been cleared.')
    return redirect(f"{reverse('accounts:user_dashboard')}#dashboard-activity-section")

@login_required
def user_dashboard_view(request):
    """User portal dashboard with follow-ups, appointments, notifications, and charts."""
    from notifications.models import FollowUp, Notification
    from appointments.models import Appointment
    from patients.models import Pet
    from pos.models import Sale, SaleItem
    from decimal import Decimal
    import json
    from dateutil.relativedelta import relativedelta

    today = date.today()

    # Pet count and pets list
    user_pets = request.user.pets.all()
    pet_count = user_pets.count()

    # Upcoming appointments (next 7 days) - filter out deleted pets
    upcoming_appointments = Appointment.objects.filter(
        user=request.user,
        pet__isnull=False,
        appointment_date__gte=today,
        appointment_date__lte=today + timedelta(days=7),
    ).exclude(status='CANCELLED').select_related(
        'branch', 'preferred_vet'
    ).order_by('appointment_date', 'appointment_time')
    upcoming_count = upcoming_appointments.count()
    
    # Confirmed vs pending for upcoming
    upcoming_confirmed = upcoming_appointments.filter(status='CONFIRMED').count()
    upcoming_pending = upcoming_appointments.filter(status='PENDING').count()

    # Follow-ups for this user's appointments
    follow_ups = FollowUp.objects.filter(
        appointment__user=request.user,
        is_completed=False,
        follow_up_date__gte=today,
    ).order_by('follow_up_date')
    follow_up_count = follow_ups.count()
    
    # Overdue follow-ups
    overdue_follow_ups = FollowUp.objects.filter(
        appointment__user=request.user,
        is_completed=False,
        follow_up_date__lt=today,
    ).count()

    # Unread notifications
    unread_notif_count = Notification.scoped_for_user(request.user).filter(
        is_read=False
    ).count()

    # Recent activities (UserActivity)
    from accounts.models import UserActivity
    activities_list = UserActivity.objects.filter(user=request.user).order_by('-timestamp')
    
    paginator = Paginator(activities_list, 5)
    page_number = request.GET.get('page')
    recent_activities = paginator.get_page(page_number)

    # Pet species breakdown with percentages
    pet_species_breakdown = list(request.user.pets.values('species').annotate(count=Count('id')).order_by('-count'))
    for species in pet_species_breakdown:
        species['percentage'] = round((species['count'] / pet_count * 100), 1) if pet_count > 0 else 0
    pet_species_json = json.dumps(pet_species_breakdown)

    # Vaccination appointments tracking
    vaccination_appointments = Appointment.objects.filter(
        user=request.user,
        pet__isnull=False,
        reason_for_visit__code='VACCINATION',
        appointment_date__gte=today - timedelta(days=30),
        appointment_date__lte=today,
    ).count()

    # Appointment cancellation stats (past 30 days)
    cancelled_appointments_count = Appointment.objects.filter(
        user=request.user,
        status='CANCELLED',
        appointment_date__gte=today - timedelta(days=30),
    ).count()

    # Appointments this month
    month_start = date(today.year, today.month, 1)
    if today.month == 12:
        month_end = date(today.year + 1, 1, 1) - timedelta(days=1)
    else:
        month_end = date(today.year, today.month + 1, 1) - timedelta(days=1)
    
    appointments_this_month = Appointment.objects.filter(
        user=request.user,
        pet__isnull=False,
        appointment_date__range=[month_start, month_end],
    ).exclude(status='CANCELLED').count()

    # Reservation tracking (pending/approved)
    pending_reservations = Appointment.objects.filter(
        user=request.user,
        pet__isnull=False,
        status='PENDING',
        appointment_date__gte=today,
    ).count()

    approved_reservations = Appointment.objects.filter(
        user=request.user,
        pet__isnull=False,
        status='CONFIRMED',
        appointment_date__gte=today,
    ).count()

    # ═══════════════════════════════════════════════════════════════════════════
    # NEW: Spending & Financial Data
    # ═══════════════════════════════════════════════════════════════════════════
    
    # Total spending (this year)
    year_start = date(today.year, 1, 1)
    total_spent_this_year = Sale.objects.filter(
        customer=request.user,
        status='COMPLETED',
        completed_at__date__gte=year_start
    ).aggregate(total=Sum('total'))['total'] or Decimal('0.00')
    
    # Total spending (all time)
    total_spent_all_time = Sale.objects.filter(
        customer=request.user,
        status='COMPLETED'
    ).aggregate(total=Sum('total'))['total'] or Decimal('0.00')
    
    # Spending breakdown by service category
    spending_by_category = SaleItem.objects.filter(
        sale__customer=request.user,
        sale__status='COMPLETED'
    ).values('item_type').annotate(
        total=Sum(F('unit_price') * F('quantity') - F('discount'))
    ).order_by('-total')
    
    category_labels = {
        'SERVICE': 'Services',
        'PRODUCT': 'Products',
        'MEDICATION': 'Medications'
    }
    spending_breakdown = []
    for item in spending_by_category:
        spending_breakdown.append({
            'category': category_labels.get(item['item_type'], item['item_type']),
            'total': float(item['total'] or 0)
        })
    spending_breakdown_json = json.dumps(spending_breakdown)

    # ═══════════════════════════════════════════════════════════════════════════
    # NEW: Monthly Appointment History (last 6 months)
    # ═══════════════════════════════════════════════════════════════════════════
    
    monthly_appointments = []
    for i in range(5, -1, -1):
        m_start = get_month_offset(today, i)
        if m_start.month == 12:
            m_end = date(m_start.year + 1, 1, 1) - timedelta(days=1)
        else:
            m_end = date(m_start.year, m_start.month + 1, 1) - timedelta(days=1)
        
        count = Appointment.objects.filter(
            user=request.user,
            pet__isnull=False,
            appointment_date__range=[m_start, m_end]
        ).exclude(status='CANCELLED').count()
        
        monthly_appointments.append({
            'month': m_start.strftime('%b'),
            'count': count
        })
    monthly_appointments_json = json.dumps(monthly_appointments)

    # ═══════════════════════════════════════════════════════════════════════════
    # NEW: Pet Health Status Distribution
    # ═══════════════════════════════════════════════════════════════════════════
    
    pet_health_stats = list(
        user_pets.values('clinical_status__code').annotate(count=Count('id')).order_by('-count')
    )
    health_labels = {
        'HEALTHY': 'Healthy',
        'MONITOR': 'Monitoring',
        'TREATMENT': 'In Treatment',
        'SURGERY': 'Post-Surgery',
        'DIAGNOSTICS': 'Diagnostics',
        'CRITICAL': 'Critical'
    }
    pet_health_breakdown = []
    for stat in pet_health_stats:
        status_code = stat['clinical_status__code'] or 'HEALTHY'
        pet_health_breakdown.append({
            'status': health_labels.get(status_code, status_code),
            'count': stat['count']
        })
    pet_health_json = json.dumps(pet_health_breakdown)

    # ═══════════════════════════════════════════════════════════════════════════
    # NEW: Appointment Status Distribution (for chart)
    # ═══════════════════════════════════════════════════════════════════════════
    
    appointment_status_stats = Appointment.objects.filter(
        user=request.user,
        pet__isnull=False,
        appointment_date__gte=today - timedelta(days=90)
    ).values('status').annotate(count=Count('id')).order_by('-count')
    
    status_labels = {
        'PENDING': 'Pending',
        'CONFIRMED': 'Confirmed',
        'COMPLETED': 'Completed',
        'CANCELLED': 'Cancelled'
    }
    appointment_status_breakdown = []
    for stat in appointment_status_stats:
        appointment_status_breakdown.append({
            'status': status_labels.get(stat['status'], stat['status']),
            'count': stat['count']
        })
    appointment_status_json = json.dumps(appointment_status_breakdown)

    # ═══════════════════════════════════════════════════════════════════════════
    # NEW: Visits per Pet (for chart)
    # ═══════════════════════════════════════════════════════════════════════════
    
    visits_per_pet = Appointment.objects.filter(
        user=request.user,
        pet__isnull=False
    ).exclude(status='CANCELLED').values('pet__name').annotate(
        visits=Count('id')
    ).order_by('-visits')[:6]
    visits_per_pet_json = json.dumps(list(visits_per_pet))

    # ═══════════════════════════════════════════════════════════════════════════
    # NEW: Recent completed appointments (for medical records section)
    # ═══════════════════════════════════════════════════════════════════════════
    
    recent_completed = Appointment.objects.filter(
        user=request.user,
        pet__isnull=False,
        status='COMPLETED'
    ).select_related('branch', 'preferred_vet', 'pet').order_by('-appointment_date')[:5]

    # Upcoming appointments pagination
    paginator_upcoming = Paginator(upcoming_appointments, 3)
    upcoming_page_number = request.GET.get('upcoming_page')
    paginated_upcoming = paginator_upcoming.get_page(upcoming_page_number)

    return render(request, 'accounts/user_dashboard.html', {
        # Basic stats
        'pet_count': pet_count,
        'upcoming_appointments': paginated_upcoming,
        'upcoming_count': upcoming_count,
        'upcoming_confirmed': upcoming_confirmed,
        'upcoming_pending': upcoming_pending,
        'follow_ups': follow_ups,
        'follow_up_count': follow_up_count,
        'overdue_follow_ups': overdue_follow_ups,
        'unread_notif_count': unread_notif_count,
        'recent_activities': recent_activities,
        'pet_species_breakdown': pet_species_breakdown,
        'pet_species_json': pet_species_json,
        'vaccination_appointments': vaccination_appointments,
        'cancelled_appointments_count': cancelled_appointments_count,
        'appointments_this_month': appointments_this_month,
        'pending_reservations': pending_reservations,
        'approved_reservations': approved_reservations,
        
        # New: Financial data
        'total_spent_this_year': total_spent_this_year,
        'total_spent_all_time': total_spent_all_time,
        'spending_breakdown_json': spending_breakdown_json,
        
        # New: Chart data
        'monthly_appointments_json': monthly_appointments_json,
        'pet_health_json': pet_health_json,
        'appointment_status_json': appointment_status_json,
        'visits_per_pet_json': visits_per_pet_json,
        
        # New: Recent medical records
        'recent_completed': recent_completed,
    })


@login_required
def profile_view(request):
    """User profile page."""
    from .forms import UserProfileUpdateForm
    if request.method == 'POST':
        form = UserProfileUpdateForm(
            request.POST, request.FILES, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Your profile was successfully updated.')
            return redirect('profile')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = UserProfileUpdateForm(instance=request.user)

    if request.user.is_clinic_staff():
        template_name = 'accounts/profile_admin.html'
    else:
        template_name = 'accounts/profile.html'

    return render(request, template_name, {
        'user': request.user,
        'form': form,
    })


@login_required
@staff_only
def admin_dashboard_view(request):
    """Admin portal dashboard — restricted to clinic staff roles."""
    from appointments.models import Appointment
    from patients.models import Pet
    from employees.models import StaffMember
    from notifications.models import Notification
    from pos.models import Sale, Payment, SaleItem
    from inventory.models import Product
    from billing.models import Service
    from inquiries.models import Inquiry

    # Check if user is a veterinarian and redirect to vet dashboard
    if request.user.assigned_role and request.user.assigned_role.code == 'veterinarian':
        return redirect('vet_dashboard')

    # Check if user is a vet assistant and redirect to vet dashboard
    if request.user.assigned_role and request.user.assigned_role.code == 'vet_assistant':
        return redirect('vet_dashboard')

    # Check if user is a receptionist and redirect to receptionist dashboard
    if request.user.assigned_role and request.user.assigned_role.code == 'receptionist':
        return redirect('receptionist_dashboard')

    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)

    # ── Today's appointments (filter out deleted pets) ──
    todays_appointments = Appointment.objects.filter(
        appointment_date=today,
        pet__isnull=False,
    ).select_related('branch', 'preferred_vet').order_by('appointment_time')

    today_count = todays_appointments.count()
    today_confirmed = todays_appointments.filter(status='CONFIRMED').count()
    today_pending = todays_appointments.filter(status='PENDING').count()

    # ── Active patients ──
    patient_count = Pet.objects.count()

    # ── Staff ──
    total_staff = StaffMember.objects.count()
    active_staff = StaffMember.objects.filter(is_active=True).count()

    # ── Branches ──
    branches = Branch.objects.filter(is_active=True)

    # ── Recent appointments (activity) ──
    # Filter out appointments where the pet has been deleted (pet=NULL)
    recent_appointments = Appointment.objects.filter(
        pet__isnull=False
    ).select_related(
        'branch', 'preferred_vet'
    ).order_by('-created_at')[:5]

    # ── Unread notifications ──
    unread_notif_count = Notification.scoped_for_user(request.user).filter(
        is_read=False
    ).count()

    # ─── COMPREHENSIVE ANALYTICS ───

    # Revenue chart data (last 7 days)
    revenue_by_day = []
    for i in range(7):
        day = today - timedelta(days=6-i)
        daily_revenue = Sale.objects.filter(
            branch=request.user.branch,
            created_at__date=day,
            status='COMPLETED'
        ).aggregate(total=Sum('total'))['total'] or 0
        revenue_by_day.append({
            'date': day.strftime('%a'),
            'revenue': float(daily_revenue)
        })

    # Monthly revenue chart data (last 6 months)
    monthly_revenue_data = []
    for i in range(6):
        # Calculate the first day of the month, i months ago
        if i == 0:
            # Current month
            month_start = today.replace(day=1)
        else:
            # Previous months
            if today.month - i <= 0:
                month_start = today.replace(year=today.year - 1, month=today.month - i + 12, day=1)
            else:
                month_start = today.replace(month=today.month - i, day=1)
        
        # Calculate the last day of that month
        if month_start.month == 12:
            month_end = month_start.replace(year=month_start.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            month_end = month_start.replace(month=month_start.month + 1, day=1) - timedelta(days=1)
        
        # Calculate revenue for that month
        if request.user.is_admin_role():  # HQ admin sees all branches
            monthly_revenue = Sale.objects.filter(
                created_at__date__range=[month_start, month_end],
                status='COMPLETED'
            ).aggregate(total=Sum('total'))['total'] or 0
        else:  # Branch admin sees only their branch
            monthly_revenue = Sale.objects.filter(
                branch=request.user.branch,
                created_at__date__range=[month_start, month_end],
                status='COMPLETED'
            ).aggregate(total=Sum('total'))['total'] or 0
            
        monthly_revenue_data.insert(0, {  # Insert at beginning to maintain chronological order
            'month': month_start.strftime('%b %Y'),
            'revenue': float(monthly_revenue)
        })

    # Appointment by status breakdown
    appointment_status_breakdown = [
        {'status': 'Pending', 'count': Appointment.objects.filter(status='PENDING', pet__isnull=False).count()},
        {'status': 'Confirmed', 'count': Appointment.objects.filter(status='CONFIRMED', pet__isnull=False).count()},
        {'status': 'Completed', 'count': Appointment.objects.filter(status='COMPLETED', pet__isnull=False).count()},
        {'status': 'Cancelled', 'count': Appointment.objects.filter(status='CANCELLED', pet__isnull=False).count()},
    ]

    # ─── WEEKLY PERFORMANCE COMPARISON DATA ───
    last_week_start = week_start - timedelta(days=7)
    last_week_end = week_start - timedelta(days=1)
    
    # This week metrics
    this_week_appointments = Appointment.objects.filter(
        appointment_date__gte=week_start,
        appointment_date__lte=week_end,
        pet__isnull=False
    ).count()
    
    this_week_completed = Appointment.objects.filter(
        appointment_date__gte=week_start,
        appointment_date__lte=week_end,
        pet__isnull=False,
        status='COMPLETED'
    ).count()
    
    this_week_revenue = Sale.objects.filter(
        created_at__date__gte=week_start,
        created_at__date__lte=week_end,
        status='COMPLETED'
    ).aggregate(total=Sum('total'))['total'] or 0
    this_week_revenue_k = round(float(this_week_revenue) / 1000, 1)
    
    this_week_products = SaleItem.objects.filter(
        sale__created_at__date__gte=week_start,
        sale__created_at__date__lte=week_end,
        sale__status='COMPLETED'
    ).aggregate(total=Sum('quantity'))['total'] or 0
    
    # Last week metrics
    last_week_appointments = Appointment.objects.filter(
        appointment_date__gte=last_week_start,
        appointment_date__lte=last_week_end,
        pet__isnull=False
    ).count()
    
    last_week_completed = Appointment.objects.filter(
        appointment_date__gte=last_week_start,
        appointment_date__lte=last_week_end,
        pet__isnull=False,
        status='COMPLETED'
    ).count()
    
    last_week_customers = User.objects.filter(
        date_joined__date__gte=last_week_start,
        date_joined__date__lte=last_week_end
    ).count()
    
    last_week_revenue = Sale.objects.filter(
        created_at__date__gte=last_week_start,
        created_at__date__lte=last_week_end,
        status='COMPLETED'
    ).aggregate(total=Sum('total'))['total'] or 0
    last_week_revenue_k = round(float(last_week_revenue) / 1000, 1)
    
    last_week_products = SaleItem.objects.filter(
        sale__created_at__date__gte=last_week_start,
        sale__created_at__date__lte=last_week_end,
        sale__status='COMPLETED'
    ).aggregate(total=Sum('quantity'))['total'] or 0

    # Branch-wise appointment statistics
    branch_appointments = Branch.objects.filter(is_active=True).annotate(
        appointment_count=Count('appointments', filter=Q(appointments__pet__isnull=False)),
        completed_count=Count('appointments', filter=Q(
            appointments__pet__isnull=False,
            appointments__status='COMPLETED'
        ))
    ).values('name', 'appointment_count', 'completed_count')

    # Staff performance metrics
    staff_performance = StaffMember.objects.filter(is_active=True).annotate(
        total_appointments=Count('appointments', filter=Q(appointments__pet__isnull=False)),
        completed_appointments=Count('appointments', filter=Q(
            appointments__pet__isnull=False,
            appointments__status='COMPLETED'
        ))
    ).values('first_name', 'last_name', 'total_appointments', 'completed_appointments')

    # Inventory value calculation
    total_inventory_value = sum(
        product.inventory_value for product in Product.objects.all()
    ) or 0

    # Expiring products list (next 30 days)
    expiring_products = Product.objects.filter(
        expiration_date__isnull=False,
        expiration_date__gte=today,
        expiration_date__lte=today + timedelta(days=30),
        is_available=True
    ).order_by('expiration_date')[:10]

    # Pet species breakdown
    pet_species_breakdown_query = Pet.objects.values('species').annotate(
        count=Count('id')
    ).order_by('-count')
    
    # Convert to list and calculate percentages
    pet_species_breakdown = list(pet_species_breakdown_query)
    if pet_species_breakdown:
        max_count = pet_species_breakdown[0]['count'] or 1
        pet_count = sum(item['count'] for item in pet_species_breakdown)
        for species in pet_species_breakdown:
            species['percentage'] = (species['count'] / pet_count * 100) if pet_count > 0 else 0

    # Appointment sources (WALKIN vs PORTAL)
    appointment_sources = {
        'WALKIN': Appointment.objects.filter(
            source='WALKIN', pet__isnull=False
        ).count(),
        'PORTAL': Appointment.objects.filter(
            source='PORTAL', pet__isnull=False
        ).count(),
    }

    # Business metrics
    total_revenue_this_week = Sale.objects.filter(
        created_at__date__range=[week_start, week_end],
        status='COMPLETED'
    ).aggregate(total=Sum('total'))['total'] or 0

    total_revenue_last_week = Sale.objects.filter(
        created_at__date__range=[week_start - timedelta(days=7), week_start - timedelta(days=1)],
        status='COMPLETED'
    ).aggregate(total=Sum('total'))['total'] or 0

    revenue_growth = (
        ((total_revenue_this_week - total_revenue_last_week) / total_revenue_last_week * 100)
        if total_revenue_last_week > 0 else 0
    )

    total_cancelled = Appointment.objects.filter(
        status='CANCELLED', pet__isnull=False
    ).count()
    total_appointments = Appointment.objects.filter(
        pet__isnull=False
    ).count()
    cancellation_rate = (
        (total_cancelled / total_appointments * 100)
        if total_appointments > 0 else 0
    )

    # New patients this week
    new_patients_this_week = Pet.objects.filter(
        created_at__date__range=[week_start, today]
    ).count()

    # Customer analytics (new vs returning)
    new_customers_this_week = Appointment.objects.filter(
        created_at__date__range=[week_start, today],
        is_returning_customer=False,
        pet__isnull=False
    ).values('user').distinct().count()

    returning_customers_this_week = Appointment.objects.filter(
        created_at__date__range=[week_start, today],
        is_returning_customer=True,
        pet__isnull=False
    ).values('user').distinct().count()

    # Service breakdown (consultation types)
    service_breakdown_query = Service.objects.filter(
        branch=request.user.branch
    ).annotate(
        usage_count=Count('sale_items__sale', filter=Q(sale_items__sale__status='COMPLETED'))
    ).values('name', 'usage_count').order_by('-usage_count')[:10]
    
    # Convert to list and calculate percentages
    service_breakdown = list(service_breakdown_query)
    if service_breakdown:
        max_count = service_breakdown[0]['usage_count'] or 1
        for service in service_breakdown:
            service['percentage'] = (service['usage_count'] / max_count * 100) if max_count > 0 else 0

    # Payment method statistics
    payment_method_stats = Payment.objects.filter(
        sale__status='COMPLETED'
    ).values('method').annotate(
        count=Count('id'),
        total=Sum('amount')
    ).order_by('-count')

    # Pet health status distribution
    pet_health_stats = [
        {'status': 'HEALTHY', 'count': Pet.objects.filter(clinical_status__code='HEALTHY').count()},
        {'status': 'MONITOR', 'count': Pet.objects.filter(clinical_status__code='MONITOR').count()},
        {'status': 'TREATMENT', 'count': Pet.objects.filter(clinical_status__code='TREATMENT').count()},
        {'status': 'SURGERY', 'count': Pet.objects.filter(clinical_status__code='SURGERY').count()},
        {'status': 'DIAGNOSTICS', 'count': Pet.objects.filter(clinical_status__code='DIAGNOSTICS').count()},
        {'status': 'CRITICAL', 'count': Pet.objects.filter(clinical_status__code='CRITICAL').count()},
    ]

    # Low stock alerts and refunds
    low_stock_products = Product.objects.filter(
        stock_quantity__lte=F('min_stock_level'),
        is_available=True
    ).order_by('stock_quantity')[:10]
    
    low_stock_count = low_stock_products.count()

    refunds_today = Sale.objects.filter(
        created_at__date=today,
        status='REFUNDED'
    ).aggregate(total=Sum('total'))['total'] or 0

    # ── New Inquiries ──
    # Wrap in try/except in case migrations haven't been run yet
    try:
        new_inquiry_count = Inquiry.objects.filter(status='NEW').count()
        recent_inquiries = Inquiry.objects.filter(
            status='NEW'
        ).select_related('branch').order_by('-created_at')[:5]
    except Exception:
        # Table doesn't exist yet (migrations not run)
        new_inquiry_count = 0
        recent_inquiries = []

    # ═══════════════════════════════════════════════════════════════════════
    # MULTI-BRANCH ANALYTICS (HQ VIEW)
    # ═══════════════════════════════════════════════════════════════════════

    # Check if user is HQ admin (can see all branches)
    is_hq_admin = request.user.hierarchy_level >= 10 if hasattr(request.user, 'hierarchy_level') else False

    # Branch Customer Distribution (This Week) - for pie chart with percentages
    branch_customer_data = []
    total_customers_all_branches = 0
    
    for branch in branches:
        # Count unique customers (users) with appointments this week at this branch
        customer_count = Appointment.objects.filter(
            branch=branch,
            appointment_date__gte=week_start,
            appointment_date__lte=week_end,
            pet__isnull=False
        ).values('user').distinct().count()
        
        # Count walk-in appointments (no user) as separate customers
        walkin_count = Appointment.objects.filter(
            branch=branch,
            appointment_date__gte=week_start,
            appointment_date__lte=week_end,
            pet__isnull=False,
            user__isnull=True
        ).count()
        
        total_branch_customers = customer_count + walkin_count
        total_customers_all_branches += total_branch_customers
        
        branch_customer_data.append({
            'name': branch.name,
            'customers': total_branch_customers,
            'percentage': 0  # Will calculate after totaling
        })
    
    # Calculate percentages
    for branch_data in branch_customer_data:
        if total_customers_all_branches > 0:
            branch_data['percentage'] = round(
                (branch_data['customers'] / total_customers_all_branches) * 100, 1
            )

    # Branch Revenue Comparison (This Week)
    branch_revenue_data = []
    total_revenue_all_branches = Decimal('0')
    
    for branch in branches:
        branch_revenue = Sale.objects.filter(
            branch=branch,
            created_at__date__gte=week_start,
            created_at__date__lte=week_end,
            status='COMPLETED'
        ).aggregate(total=Sum('total'))['total'] or Decimal('0')
        
        total_revenue_all_branches += branch_revenue
        
        branch_revenue_data.append({
            'name': branch.name,
            'revenue': float(branch_revenue),
            'percentage': 0
        })
    
    # Calculate revenue percentages
    for branch_data in branch_revenue_data:
        if total_revenue_all_branches > 0:
            branch_data['percentage'] = round(
                (Decimal(str(branch_data['revenue'])) / total_revenue_all_branches) * 100, 1
            )

    # Branch Appointment Count (This Week)
    branch_appointment_data = []
    total_appointments_all_branches = 0
    
    for branch in branches:
        appt_count = Appointment.objects.filter(
            branch=branch,
            appointment_date__gte=week_start,
            appointment_date__lte=week_end,
            pet__isnull=False
        ).count()
        
        total_appointments_all_branches += appt_count
        
        branch_appointment_data.append({
            'name': branch.name,
            'appointments': appt_count,
            'percentage': 0
        })
    
    # Calculate appointment percentages
    for branch_data in branch_appointment_data:
        if total_appointments_all_branches > 0:
            branch_data['percentage'] = round(
                (branch_data['appointments'] / total_appointments_all_branches) * 100, 1
            )

    # Branch Trend Data (Last 7 Days) - for multi-line chart
    branch_trend_data = {branch.name: [] for branch in branches}
    trend_labels = []
    
    for i in range(7):
        day = today - timedelta(days=6-i)
        trend_labels.append(day.strftime('%a'))
        
        for branch in branches:
            day_customers = Appointment.objects.filter(
                branch=branch,
                appointment_date=day,
                pet__isnull=False
            ).values('user').distinct().count()
            
            # Add walk-ins
            day_walkins = Appointment.objects.filter(
                branch=branch,
                appointment_date=day,
                pet__isnull=False,
                user__isnull=True
            ).count()
            
            branch_trend_data[branch.name].append(day_customers + day_walkins)

    # Monthly Branch Performance (Last 6 months)
    branch_monthly_data = {branch.name: [] for branch in branches}
    monthly_labels = []
    
    for i in range(5, -1, -1):
        # Calculate month offset
        month_date = today.replace(day=1)
        for _ in range(i):
            month_date = (month_date - timedelta(days=1)).replace(day=1)
        
        monthly_labels.append(month_date.strftime('%b'))
        
        # Get last day of month
        if month_date.month == 12:
            next_month = month_date.replace(year=month_date.year + 1, month=1)
        else:
            next_month = month_date.replace(month=month_date.month + 1)
        last_day = (next_month - timedelta(days=1)).day
        month_end = month_date.replace(day=last_day)
        
        for branch in branches:
            monthly_customers = Appointment.objects.filter(
                branch=branch,
                appointment_date__gte=month_date,
                appointment_date__lte=month_end,
                pet__isnull=False
            ).values('user').distinct().count()
            
            branch_monthly_data[branch.name].append(monthly_customers)

    # Branch colors for consistent styling
    branch_colors = ['#009688', '#00BCD4', '#4CAF50', '#FF9800', '#E91E63', '#9C27B0']

    # Convert data to JSON for charts (use DjangoJSONEncoder for Decimal support)
    revenue_by_day_json = json.dumps(revenue_by_day, cls=DjangoJSONEncoder)
    monthly_revenue_data_json = json.dumps(monthly_revenue_data, cls=DjangoJSONEncoder)
    appointment_status_breakdown_json = json.dumps(appointment_status_breakdown, cls=DjangoJSONEncoder)
    pet_species_breakdown_json = json.dumps(pet_species_breakdown, cls=DjangoJSONEncoder)
    payment_method_stats_list = list(payment_method_stats)
    payment_method_stats_json = json.dumps(payment_method_stats_list, cls=DjangoJSONEncoder)
    appointment_sources_json = json.dumps([
        {'source': 'Walk-in', 'count': appointment_sources['WALKIN']},
        {'source': 'Online Portal', 'count': appointment_sources['PORTAL']}
    ], cls=DjangoJSONEncoder)
    
    # Multi-branch chart data JSON
    branch_customer_json = json.dumps(branch_customer_data, cls=DjangoJSONEncoder)
    branch_revenue_json = json.dumps(branch_revenue_data, cls=DjangoJSONEncoder)
    branch_appointment_json = json.dumps(branch_appointment_data, cls=DjangoJSONEncoder)
    branch_trend_json = json.dumps({
        'labels': trend_labels,
        'datasets': branch_trend_data
    }, cls=DjangoJSONEncoder)
    branch_monthly_json = json.dumps({
        'labels': monthly_labels,
        'datasets': branch_monthly_data
    }, cls=DjangoJSONEncoder)
    branch_colors_json = json.dumps(branch_colors[:len(branches)], cls=DjangoJSONEncoder)

    return render(request, 'accounts/admin_dashboard.html', {
        'today_count': today_count,
        'today_confirmed': today_confirmed,
        'today_pending': today_pending,
        'patient_count': patient_count,
        'total_staff': total_staff,
        'active_staff': active_staff,
        'branches': branches,
        'todays_appointments': todays_appointments[:10],
        'recent_appointments': recent_appointments,
        'unread_notif_count': unread_notif_count,
        'revenue_by_day': revenue_by_day_json,
        'monthly_revenue_data': monthly_revenue_data_json,
        'appointment_status_breakdown': appointment_status_breakdown_json,
        'branch_appointments': branch_appointments,
        'staff_performance': staff_performance,
        'total_inventory_value': total_inventory_value,
        'expiring_products': expiring_products,
        'pet_species_breakdown': pet_species_breakdown,
        'pet_species_breakdown_json': pet_species_breakdown_json,
        'appointment_sources': appointment_sources,
        'appointment_sources_json': appointment_sources_json,
        'revenue_growth': revenue_growth,
        'cancellation_rate': cancellation_rate,
        'new_patients_this_week': new_patients_this_week,
        'new_customers_this_week': new_customers_this_week,
        'returning_customers_this_week': returning_customers_this_week,
        'service_breakdown': service_breakdown,
        'payment_method_stats': payment_method_stats_list,
        'payment_method_stats_json': payment_method_stats_json,
        'pet_health_stats': pet_health_stats,
        'low_stock_products': low_stock_products,
        'low_stock_count': low_stock_count,
        'refunds_today': refunds_today,
        'total_revenue_this_week': total_revenue_this_week,
        'new_inquiry_count': new_inquiry_count,
        'recent_inquiries': recent_inquiries,
        # Multi-branch analytics
        'is_hq_admin': is_hq_admin,
        'branch_customer_data': branch_customer_data,
        'branch_customer_json': branch_customer_json,
        'branch_revenue_data': branch_revenue_data,
        'branch_revenue_json': branch_revenue_json,
        'branch_appointment_data': branch_appointment_data,
        'branch_appointment_json': branch_appointment_json,
        'branch_trend_json': branch_trend_json,
        'branch_monthly_json': branch_monthly_json,
        'branch_colors_json': branch_colors_json,
        'total_customers_all_branches': total_customers_all_branches,
        'total_revenue_all_branches': float(total_revenue_all_branches),
        'total_appointments_all_branches': total_appointments_all_branches,
        # Weekly comparison chart data
        'this_week_appointments': this_week_appointments,
        'this_week_completed': this_week_completed,
        'this_week_revenue_k': this_week_revenue_k,
        'this_week_products': this_week_products,
        'last_week_appointments': last_week_appointments,
        'last_week_completed': last_week_completed,
        'last_week_customers': last_week_customers,
        'last_week_revenue_k': last_week_revenue_k,
        'last_week_products': last_week_products,
    })


@login_required
@staff_only
def vet_dashboard_view(request):
    """Veterinarian and Vet Assistant dashboard with comprehensive statistics."""
    from appointments.models import Appointment
    from patients.models import Pet
    from employees.models import StaffMember, VetSchedule
    from notifications.models import Notification, FollowUp
    from records.models import MedicalRecord

    today = date.today()
    week_end = today + timedelta(days=7)
    month_start = date(today.year, today.month, 1)

    # Determine dashboard title based on role
    is_vet_assistant = (
        request.user.assigned_role and 
        request.user.assigned_role.code == 'vet_assistant'
    )
    dashboard_title = "Vet Assistant Dashboard" if is_vet_assistant else "Veterinarian Dashboard"

    # Get the vet's staff profile
    try:
        staff_profile = request.user.staff_profile
    except StaffMember.DoesNotExist:
        staff_profile = None

    # ── Total assigned patients (get distinct pets from vet's appointments) ──
    if staff_profile:
        assigned_patients = Pet.objects.filter(
            appointments__preferred_vet=staff_profile
        ).distinct().count()
    else:
        assigned_patients = 0

    # ── Today's appointments for this vet ──
    if staff_profile:
        todays_appointments = Appointment.objects.filter(
            appointment_date=today,
            preferred_vet=staff_profile,
            pet__isnull=False,
        ).exclude(status='CANCELLED').select_related('pet', 'branch').order_by('appointment_time')
    else:
        todays_appointments = Appointment.objects.none()

    today_count = todays_appointments.count()

    # ── Upcoming appointments (next 7 days) ──
    if staff_profile:
        upcoming_appointments = Appointment.objects.filter(
            appointment_date__gt=today,
            appointment_date__lte=week_end,
            preferred_vet=staff_profile,
            pet__isnull=False,
        ).exclude(status='CANCELLED').select_related('pet', 'branch').order_by('appointment_date', 'appointment_time')
    else:
        upcoming_appointments = Appointment.objects.none()

    upcoming_count = upcoming_appointments.count()

    # ── Completed consultations (past appointments with status COMPLETED) ──
    if staff_profile:
        completed_consultations = Appointment.objects.filter(
            preferred_vet=staff_profile,
            status='COMPLETED',
            pet__isnull=False,
        ).count()
    else:
        completed_consultations = 0

    # ── Medical records created by this vet ──
    if staff_profile:
        medical_records_count = MedicalRecord.objects.filter(
            vet=staff_profile
        ).count()
    else:
        medical_records_count = 0

    # ── Pending follow-ups for this vet's patients ──
    if staff_profile:
        follow_ups = FollowUp.objects.filter(
            appointment__preferred_vet=staff_profile,
            is_completed=False,
            follow_up_date__gte=today,
        ).select_related('appointment', 'appointment__pet').order_by('follow_up_date')[:10]
    else:
        follow_ups = FollowUp.objects.none()

    follow_up_count = follow_ups.count()

    # ── This week's schedule ──
    if staff_profile:
        this_week_schedule = VetSchedule.objects.filter(
            staff=staff_profile,
            date__gte=today,
            date__lte=week_end,
        ).select_related('branch').order_by('date', 'start_time')
    else:
        this_week_schedule = VetSchedule.objects.none()

    # ── Unread notifications ──
    unread_notif_count = Notification.scoped_for_user(request.user).filter(
        is_read=False
    ).count()

    # ─── COMPREHENSIVE ANALYTICS ───

    # Patient status distribution
    if staff_profile:
        patient_status_distribution = Pet.objects.filter(
            appointments__preferred_vet=staff_profile
        ).distinct().values('clinical_status__name').annotate(count=Count('id')).order_by('-count')
        patient_status_distribution = [
            {
                'status': row['clinical_status__name'] or 'Unassigned',
                'count': row['count'],
            }
            for row in patient_status_distribution
        ]
    else:
        patient_status_distribution = []

    # Consultation reasons breakdown
    if staff_profile:
        consultation_reasons_query = Appointment.objects.filter(
            preferred_vet=staff_profile,
            pet__isnull=False
        ).values('reason_for_visit__name').annotate(count=Count('id')).order_by('-count')
        
        # Convert to list and calculate percentages
        consultation_reasons = list(consultation_reasons_query)
        if consultation_reasons:
            for reason in consultation_reasons:
                reason['reason'] = reason.pop('reason_for_visit__name') or 'Unspecified'
            max_count = consultation_reasons[0]['count'] or 1
            for reason in consultation_reasons:
                reason['percentage'] = (reason['count'] / max_count * 100) if max_count > 0 else 0
    else:
        consultation_reasons = []

    # Average daily consultations (last 30 days)
    if staff_profile:
        consultations_last_30_days = Appointment.objects.filter(
            preferred_vet=staff_profile,
            appointment_date__range=[today - timedelta(days=30), today],
            status='COMPLETED',
            pet__isnull=False
        ).count()
        avg_daily_consultations = consultations_last_30_days / 30 if consultations_last_30_days > 0 else 0
    else:
        avg_daily_consultations = 0

    # New vs returning patients (this month)
    if staff_profile:
        new_patients_this_month = Pet.objects.filter(
            appointments__preferred_vet=staff_profile,
            created_at__date__range=[month_start, today]
        ).distinct().count()

        returning_patients_this_month = Appointment.objects.filter(
            preferred_vet=staff_profile,
            appointment_date__range=[month_start, today],
            is_returning_customer=True,
            pet__isnull=False
        ).values('pet').distinct().count()
    else:
        new_patients_this_month = 0
        returning_patients_this_month = 0

    # Surgeries count (this month)
    if staff_profile:
        surgeries_this_month = Appointment.objects.filter(
            preferred_vet=staff_profile,
            appointment_date__range=[month_start, today],
            reason_for_visit__code='SURGERY',
            pet__isnull=False
        ).count()
    else:
        surgeries_this_month = 0

    # Emergency cases count
    if staff_profile:
        emergency_cases = Appointment.objects.filter(
            preferred_vet=staff_profile,
            reason_for_visit__code='EMERGENCY',
            pet__isnull=False
        ).count()
    else:
        emergency_cases = 0

    # Vaccinations count
    if staff_profile:
        vaccinations_count = Appointment.objects.filter(
            preferred_vet=staff_profile,
            reason_for_visit__code='VACCINATION',
            pet__isnull=False
        ).count()
    else:
        vaccinations_count = 0

    # Medical records created this month
    if staff_profile:
        medical_records_this_month = MedicalRecord.objects.filter(
            vet=staff_profile,
            date_recorded__range=[month_start, today]
        ).count()
    else:
        medical_records_this_month = 0

    # ── Weekly workload data (appointments per day this week) ──
    weekly_workload = []
    # Calculate start of the week (Sunday)
    day_of_week = today.weekday()  # Monday=0, Sunday=6
    # Adjust to make Sunday = 0
    days_since_sunday = (day_of_week + 1) % 7
    start_of_week = today - timedelta(days=days_since_sunday)
    
    for i in range(7):
        day_date = start_of_week + timedelta(days=i)
        if staff_profile and day_date <= today:
            day_count = Appointment.objects.filter(
                appointment_date=day_date,
                preferred_vet=staff_profile,
                pet__isnull=False,
            ).exclude(status='CANCELLED').count()
        else:
            day_count = 0
        weekly_workload.append(day_count)

    # ── Monthly performance data (last 6 months) ──
    monthly_consultations = []
    monthly_patients = []
    monthly_labels = []
    
    for i in range(5, -1, -1):  # 5 months ago to current month
        # Calculate the first and last day of each month
        target_date = today - timedelta(days=i * 30)  # Approximate
        target_month_start = date(target_date.year, target_date.month, 1)
        if target_date.month == 12:
            target_month_end = date(target_date.year + 1, 1, 1) - timedelta(days=1)
        else:
            target_month_end = date(target_date.year, target_date.month + 1, 1) - timedelta(days=1)
        
        # Don't query future dates
        if target_month_end > today:
            target_month_end = today
        
        monthly_labels.append(target_month_start.strftime('%b'))
        
        if staff_profile:
            # Consultations (completed appointments)
            consultations = Appointment.objects.filter(
                preferred_vet=staff_profile,
                appointment_date__range=[target_month_start, target_month_end],
                status='COMPLETED',
                pet__isnull=False
            ).count()
            monthly_consultations.append(consultations)
            
            # Patients seen (unique pets)
            patients = Pet.objects.filter(
                appointments__preferred_vet=staff_profile,
                appointments__appointment_date__range=[target_month_start, target_month_end]
            ).distinct().count()
            monthly_patients.append(patients)
        else:
            monthly_consultations.append(0)
            monthly_patients.append(0)

    return render(request, 'accounts/vet_dashboard.html', {
        'staff_profile': staff_profile,
        'assigned_patients': assigned_patients,
        'today_count': today_count,
        'todays_appointments': todays_appointments[:10],
        'upcoming_count': upcoming_count,
        'upcoming_appointments': upcoming_appointments[:10],
        'completed_consultations': completed_consultations,
        'medical_records_count': medical_records_count,
        'follow_up_count': follow_up_count,
        'follow_ups': follow_ups,
        'this_week_schedule': this_week_schedule,
        'unread_notif_count': unread_notif_count,
        'patient_status_distribution': patient_status_distribution,
        'consultation_reasons': consultation_reasons,
        'avg_daily_consultations': avg_daily_consultations,
        'new_patients_this_month': new_patients_this_month,
        'returning_patients_this_month': returning_patients_this_month,
        'surgeries_this_month': surgeries_this_month,
        'emergency_cases': emergency_cases,
        'vaccinations_count': vaccinations_count,
        'medical_records_this_month': medical_records_this_month,
        'today': today,  # For follow-up date comparison
        'dashboard_title': dashboard_title,  # Dynamic title for vet/vet assistant
        'is_vet_assistant': is_vet_assistant,
        # Weekly and monthly chart data
        'weekly_workload': weekly_workload,
        'monthly_consultations': monthly_consultations,
        'monthly_patients': monthly_patients,
        'monthly_labels': monthly_labels,
    })


@login_required
@staff_only
def receptionist_dashboard_view(request):
    """Receptionist-specific dashboard with POS, appointments, and customer management focus."""
    from appointments.models import Appointment
    from patients.models import Pet
    from pos.models import Sale, Payment, SaleItem
    from notifications.models import Notification
    from inventory.models import Product, StockAdjustment

    today = date.today()
    yesterday = today - timedelta(days=1)
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    
    # Get the receptionist's assigned branch
    user_branch = request.user.branch
    
    # Branch filter - if user has a branch, filter by it; otherwise show all
    branch_filter = {'branch': user_branch} if user_branch else {}

    # ── Today's appointments (branch-specific) ──
    todays_appointments = Appointment.objects.filter(
        appointment_date=today,
        pet__isnull=False,
        **branch_filter
    ).select_related('branch', 'preferred_vet', 'pet', 'pet__owner').order_by('appointment_time')

    today_count = todays_appointments.count()
    today_confirmed = todays_appointments.filter(status='CONFIRMED').count()
    today_pending = todays_appointments.filter(status='PENDING').count()

    # ── Today's sales statistics (branch-specific) ──
    todays_sales = Sale.objects.filter(
        created_at__date=today,
        status='COMPLETED',
        **branch_filter
    )
    todays_sales_count = todays_sales.count()
    todays_revenue = sum(sale.total for sale in todays_sales) if todays_sales else 0

    # ── This week's statistics (branch-specific) ──
    weekly_sales = Sale.objects.filter(
        created_at__date__range=[week_start, week_end],
        status='COMPLETED',
        **branch_filter
    )
    weekly_sales_count = weekly_sales.count()
    weekly_revenue = sum(sale.total for sale in weekly_sales) if weekly_sales else 0

    # ── Pending tasks (branch-specific) ──
    pending_appointments = Appointment.objects.filter(
        status='PENDING',
        appointment_date__gte=today,
        **branch_filter
    ).count()


    # ── Recent sales (branch-specific) ──
    recent_sales = Sale.objects.filter(
        status__in=['COMPLETED', 'REFUNDED'],
        **branch_filter
    ).select_related('customer', 'pet').order_by('-created_at')[:5]

    # ── Upcoming appointments (next 3 days, branch-specific) ──
    upcoming_appointments = Appointment.objects.filter(
        appointment_date__range=[today + timedelta(days=1), today + timedelta(days=3)],
        pet__isnull=False,
        **branch_filter
    ).select_related('branch', 'preferred_vet').order_by('appointment_date', 'appointment_time')[:10]

    # ── Recent registrations (new pets this week) ──
    new_pets_this_week = Pet.objects.filter(
        created_at__range=[week_start, week_end]
    ).count()

    # ── Unread notifications ──
    unread_notif_count = Notification.scoped_for_user(request.user).filter(
        is_read=False
    ).count()

    # ─── COMPREHENSIVE ANALYTICS ───

    # Walk-in vs Portal appointments (today, branch-specific)
    walkin_today = Appointment.objects.filter(
        appointment_date=today,
        source='WALKIN',
        pet__isnull=False,
        **branch_filter
    ).count()
    portal_today = Appointment.objects.filter(
        appointment_date=today,
        source='PORTAL',
        pet__isnull=False,
        **branch_filter
    ).count()

    # ─── APPOINTMENT STATUS DISTRIBUTION (Today, branch-specific) ───
    appointment_status_data = []
    status_counts = Appointment.objects.filter(
        appointment_date=today,
        pet__isnull=False,
        **branch_filter
    ).values('status').annotate(count=Count('id'))
    
    for item in status_counts:
        appointment_status_data.append({
            'status': item['status'],
            'count': item['count']
        })

    # ─── WALK-IN VS PORTAL APPOINTMENTS DATA (Today, branch-specific) ───
    appointment_source_data = [
        {'source': 'Walk-in', 'count': walkin_today},
        {'source': 'Online Booking', 'count': portal_today}
    ]

    # Hourly distribution of appointments (today, branch-specific)
    hourly_distribution = Appointment.objects.filter(
        appointment_date=today,
        pet__isnull=False,
        **branch_filter
    ).values('appointment_time__hour').annotate(
        count=Count('id')
    ).order_by('appointment_time__hour')

    # Registered vs Walk-in sales (today, branch-specific)
    registered_sales_today = Sale.objects.filter(
        created_at__date=today,
        customer_type='REGISTERED',
        status='COMPLETED',
        **branch_filter
    ).aggregate(total=Sum('total'))['total'] or 0

    walkin_sales_today = Sale.objects.filter(
        created_at__date=today,
        customer_type='WALKIN',
        status='COMPLETED',
        **branch_filter
    ).aggregate(total=Sum('total'))['total'] or 0

    # Refunds today with amount (branch-specific)
    refunds_today = Sale.objects.filter(
        created_at__date=today,
        status='REFUNDED',
        **branch_filter
    )
    refunds_count = refunds_today.count()
    refunds_amount = sum(sale.total for sale in refunds_today) if refunds_today else 0

    # Pending reservations (branch-specific)
    pending_reservations = Appointment.objects.filter(
        appointment_date__gte=today,
        status='PENDING',
        pet__isnull=False,
        **branch_filter
    ).count()

    # Appointment by reason breakdown (today, branch-specific)
    appointment_reasons_today_query = Appointment.objects.filter(
        appointment_date=today,
        pet__isnull=False,
        **branch_filter
    ).values('reason_for_visit__name').annotate(
        count=Count('id')
    ).order_by('-count')
    
    # Convert to list and calculate percentages
    appointment_reasons_today = list(appointment_reasons_today_query)
    if appointment_reasons_today:
        for reason in appointment_reasons_today:
            reason['reason'] = reason.pop('reason_for_visit__name') or 'Unspecified'
        max_count = appointment_reasons_today[0]['count'] or 1
        for reason in appointment_reasons_today:
            reason['percentage'] = (reason['count'] / max_count * 100) if max_count > 0 else 0

    # Revenue comparison vs yesterday (branch-specific)
    yesterdays_revenue = Sale.objects.filter(
        created_at__date=yesterday,
        status='COMPLETED',
        **branch_filter
    ).aggregate(total=Sum('total'))['total'] or 0

    revenue_diff = float(todays_revenue) - float(yesterdays_revenue)
    revenue_diff_pct = (
        (revenue_diff / float(yesterdays_revenue) * 100)
        if yesterdays_revenue > 0 else 0
    )

    # Payment method breakdown (branch-specific)
    payment_filter = {'sale__branch': user_branch} if user_branch else {}
    payment_method_breakdown_query = Payment.objects.filter(
        sale__created_at__date=today,
        sale__status='COMPLETED',
        **payment_filter
    ).values('method').annotate(
        count=Count('id'),
        total=Sum('amount')
    ).order_by('-count')
    
    # Convert to list and calculate percentages
    payment_method_breakdown = list(payment_method_breakdown_query)
    if payment_method_breakdown:
        max_count = payment_method_breakdown[0]['count'] or 1
        for method in payment_method_breakdown:
            method['percentage'] = (method['count'] / max_count * 100) if max_count > 0 else 0

    # Check-in statistics (today, branch-specific)
    checked_in_today = Appointment.objects.filter(
        appointment_date=today,
        status='COMPLETED',
        pet__isnull=False,
        **branch_filter
    ).count()

    # ─── WEEKLY REVENUE TREND (Last 7 Days, branch-specific) ───
    weekly_revenue_data = []
    for i in range(6, -1, -1):  # Last 7 days
        day = today - timedelta(days=i)
        day_revenue = Sale.objects.filter(
            created_at__date=day,
            status='COMPLETED',
            **branch_filter
        ).aggregate(total=Sum('total'))['total'] or 0
        weekly_revenue_data.append({
            'date': day.strftime('%a'),  # Mon, Tue, etc.
            'revenue': float(day_revenue)
        })

    # ─── TOP SELLING PRODUCTS (This Week, branch-specific) ───
    product_branch_filter = {'branch': user_branch} if user_branch else {}
    top_products_query = SaleItem.objects.filter(
        sale__created_at__date__range=[week_start, today],
        sale__status='COMPLETED',
        item_type='PRODUCT',
        product__isnull=False,
        **({'sale__branch': user_branch} if user_branch else {})
    ).values('product__name').annotate(
        total_qty=Sum('quantity'),
        total_sales=Sum(F('quantity') * F('unit_price'))
    ).order_by('-total_qty')[:5]
    
    top_products = list(top_products_query)
    for product in top_products:
        product['total_sales'] = float(product['total_sales']) if product['total_sales'] else 0

    # ─── LOW STOCK PRODUCTS (branch-specific) ───
    low_stock_products = Product.objects.filter(
        is_available=True,
        stock_quantity__lte=F('min_stock_level'),
        **product_branch_filter
    ).order_by('stock_quantity')[:5]
    
    low_stock_count = Product.objects.filter(
        is_available=True,
        stock_quantity__lte=F('min_stock_level'),
        **product_branch_filter
    ).count()

    # ─── PRODUCT CATEGORY SALES (Today, branch-specific) ───
    category_sales_query = SaleItem.objects.filter(
        sale__created_at__date=today,
        sale__status='COMPLETED',
        **({'sale__branch': user_branch} if user_branch else {})
    ).values('item_type').annotate(
        count=Count('id'),
        total=Sum(F('quantity') * F('unit_price'))
    ).order_by('-total')
    
    category_sales = []
    for item in category_sales_query:
        category_sales.append({
            'type': item['item_type'],
            'count': item['count'],
            'total': float(item['total']) if item['total'] else 0
        })

    # ─── HOURLY SALES TREND (Today, branch-specific) ───
    hourly_sales_data = []
    for hour in range(8, 20):  # 8 AM to 8 PM
        hour_sales = Sale.objects.filter(
            created_at__date=today,
            created_at__hour=hour,
            status='COMPLETED',
            **branch_filter
        ).aggregate(
            count=Count('id'),
            total=Sum('total')
        )
        hourly_sales_data.append({
            'hour': f'{hour}:00',
            'count': hour_sales['count'] or 0,
            'total': float(hour_sales['total']) if hour_sales['total'] else 0
        })

    context = {
        # Branch info
        'user_branch': user_branch,
        'branch_name': user_branch.name if user_branch else 'All Branches',
        
        # Appointment stats
        'today_count': today_count,
        'today_confirmed': today_confirmed,
        'today_pending': today_pending,
        'pending_appointments': pending_appointments,
        'pending_reservations': pending_reservations,

        # Sales stats
        'todays_sales_count': todays_sales_count,
        'todays_revenue': todays_revenue,
        'weekly_sales_count': weekly_sales_count,
        'weekly_revenue': weekly_revenue,
        'registered_sales_today': float(registered_sales_today) if registered_sales_today else 0,
        'walkin_sales_today': float(walkin_sales_today) if walkin_sales_today else 0,

        # Customer stats
        'new_pets_this_week': new_pets_this_week,

        # Recent activity
        'todays_appointments': todays_appointments[:10],
        'upcoming_appointments': upcoming_appointments,
        'recent_sales': recent_sales,

        # Notifications
        'unread_notif_count': unread_notif_count,

        # Additional analytics
        'walkin_today': walkin_today,
        'portal_today': portal_today,
        'hourly_distribution': hourly_distribution,
        'refunds_count': refunds_count,
        'refunds_amount': refunds_amount,
        'appointment_reasons_today': appointment_reasons_today,
        'yesterdays_revenue': yesterdays_revenue,
        'revenue_diff': revenue_diff,
        'revenue_diff_pct': revenue_diff_pct,
        'payment_method_breakdown': json.dumps(payment_method_breakdown, cls=DjangoJSONEncoder),
        'checked_in_today': checked_in_today,
        
        # NEW: Revenue & Product Analytics
        'weekly_revenue_data': json.dumps(weekly_revenue_data, cls=DjangoJSONEncoder),
        'top_products': json.dumps(top_products, cls=DjangoJSONEncoder),
        'low_stock_products': low_stock_products,
        'low_stock_count': low_stock_count,
        'category_sales': json.dumps(category_sales, cls=DjangoJSONEncoder),
        
        # NEW: Appointment Analytics (replacing hourly sales & payment methods)
        'appointment_status_data': json.dumps(appointment_status_data, cls=DjangoJSONEncoder),
        'appointment_source_data': json.dumps(appointment_source_data, cls=DjangoJSONEncoder),
    }

    return render(request, 'accounts/receptionist_dashboard.html', context)


@login_required
@admin_only
@module_permission_required('staff', 'CREATE')
def admin_create_account(request):
    """Admin view to create new staff accounts (not Pet Owners).
    
    Staff accounts must be created through this form. Pet Owners register
    themselves via the public registration page.
    """
    from .forms import AdminAccountCreationForm
    from django.db import IntegrityError

    if request.method == 'POST':
        form = AdminAccountCreationForm(request.POST)
        if form.is_valid():
            try:
                user = form.save()

                # Auto-create StaffMember if staff role assigned
                if user.assigned_role and user.assigned_role.is_staff_role:
                    from employees.models import StaffMember
                    # Map RBAC role to StaffMember position
                    role_to_position = {
                        'veterinarian': StaffMember.Position.VETERINARIAN,
                        'vet_assistant': StaffMember.Position.VET_ASSISTANT,
                        'receptionist': StaffMember.Position.RECEPTIONIST,
                        'branch_admin': StaffMember.Position.ADMIN,
                        'superadmin': StaffMember.Position.ADMIN,
                        'admin': StaffMember.Position.ADMIN,
                    }
                    position = role_to_position.get(
                        user.assigned_role.code,
                        StaffMember.Position.RECEPTIONIST
                    )

                    # Create or update StaffMember record
                    StaffMember.objects.update_or_create(
                        user=user,
                        defaults={
                            'first_name': user.first_name,
                            'last_name': user.last_name,
                            'email': user.email,
                            'phone': user.phone_number or '',
                            'position': position,
                            'branch': user.branch,
                            'is_active': True,
                        }
                    )

                messages.success(request, f'Account created for {user.get_full_name() or user.username}.')
                return redirect('accounts:user_role_list')
            
            except IntegrityError as e:
                # Handle the case where the form validation didn't catch the duplicate
                if 'username' in str(e):
                    form.add_error('username', 'This username is already in use. Please choose another.')
                    messages.error(request, 'Username already exists. Please choose a different username.')
                elif 'email' in str(e):
                    form.add_error('email', 'This email is already in use. Please choose another.')
                    messages.error(request, 'Email already exists. Please choose a different email.')
                else:
                    form.add_error(None, 'An error occurred while creating the account. Please try again.')
                    messages.error(request, 'An error occurred while creating the account. Please check your input and try again.')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = AdminAccountCreationForm()

    return render(request, 'accounts/admin_create_account.html', {'form': form})
