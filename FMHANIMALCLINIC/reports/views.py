"""Views for Reports & Analytics module."""

import json
from datetime import datetime, timedelta
from decimal import Decimal
from calendar import monthrange

from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count, Avg, F, Q, DecimalField, ExpressionWrapper
from django.db.models.functions import TruncDate, ExtractHour
from django.utils import timezone
from django.http import HttpResponse

from accounts.decorators import module_permission_required
from accounts.models import User
from pos.models import Sale, SaleItem, Payment, Refund
from appointments.models import Appointment
from inventory.models import Product, StockAdjustment
from patients.models import Pet
from records.models import RecordEntry
from branches.models import Branch


# =============================================================================
# Analytics Dashboard (Main Reports Page)
# =============================================================================

@login_required
@module_permission_required('reports', 'VIEW')
def analytics_dashboard(request):
    """
    Professional analytics dashboard with 3 core metrics:
    1. Total Number of Patients
    2. Net Sales & Gross Sales
    3. Monthly New Clients vs. Returning Clients

    Filterable by Branch and Time Period (daily, weekly, monthly).
    """
    branch = request.user.branch
    today = timezone.now().date()

    # ── Filters ───────────────────────────────────────────────────────
    branch_id = request.GET.get('branch', '')
    period = request.GET.get('period', 'monthly')  # daily | weekly | monthly

    # Determine date range from period
    if period == 'daily':
        date_from = today
        date_to = today
        period_label = today.strftime('%B %d, %Y')
    elif period == 'weekly':
        date_from = today - timedelta(days=today.weekday())  # Monday
        date_to = date_from + timedelta(days=6)  # Sunday
        period_label = f"{date_from.strftime('%b %d')} – {date_to.strftime('%b %d, %Y')}"
    else:  # monthly (default)
        date_from = today.replace(day=1)
        _, last_day = monthrange(today.year, today.month)
        date_to = today.replace(day=last_day)
        period_label = today.strftime('%B %Y')

    # Branch filtering
    filter_branch = None
    if request.user.is_module_branch_restricted('reports') and branch:
        filter_branch = branch
    elif branch_id:
        try:
            filter_branch = Branch.objects.get(id=branch_id)
        except (Branch.DoesNotExist, ValueError):
            filter_branch = None

    # ── Metric 1: Total Patients ──────────────────────────────────────
    pets_qs = Pet.objects.filter(is_active=True)
    total_patients = pets_qs.count()
    new_patients_period = pets_qs.filter(
        created_at__date__gte=date_from,
        created_at__date__lte=date_to
    ).count()

    # ── Metric 2: Gross & Net Sales ───────────────────────────────────
    sales_qs = Sale.objects.filter(
        status=Sale.Status.COMPLETED,
        created_at__date__gte=date_from,
        created_at__date__lte=date_to,
    )
    if filter_branch:
        sales_qs = sales_qs.filter(branch=filter_branch)

    sales_agg = sales_qs.aggregate(
        gross_sales=Sum('subtotal'),
        net_sales=Sum('total'),
        transaction_count=Count('id'),
    )
    gross_sales = sales_agg['gross_sales'] or Decimal('0')
    net_sales = sales_agg['net_sales'] or Decimal('0')
    # Calculate total discount amount from percentage discounts
    total_discount = Decimal('0')
    for sale in sales_qs:
        if sale.discount_percent > 0:
            total_discount += (sale.subtotal * sale.discount_percent /
                               Decimal('100')).quantize(Decimal('0.01'))
    transaction_count = sales_agg['transaction_count'] or 0

    # Subtract Refund amounts from Net Sales
    refund_qs = Refund.objects.filter(
        status=Refund.Status.COMPLETED,
        created_at__date__gte=date_from,
        created_at__date__lte=date_to,
    )
    if filter_branch:
        refund_qs = refund_qs.filter(sale__branch=filter_branch)
    total_refunds = refund_qs.aggregate(total=Sum('amount'))[
        'total'] or Decimal('0')
    net_sales -= total_refunds

    # ── Metric 3: Monthly New vs Returning Clients ────────────────────
    # Build 12-month lookback for chart
    months_data = []
    for i in range(11, -1, -1):
        # Calculate month offset
        m_date = today.replace(day=1)
        for _ in range(i):
            m_date = (m_date - timedelta(days=1)).replace(day=1)

        m_start = m_date
        _, m_last = monthrange(m_date.year, m_date.month)
        m_end = m_date.replace(day=m_last)

        # Client counts
        appts_qs = Appointment.objects.filter(
            appointment_date__gte=m_start,
            appointment_date__lte=m_end,
        ).exclude(status='CANCELLED')
        if filter_branch:
            appts_qs = appts_qs.filter(branch=filter_branch)

        new_count = appts_qs.filter(is_returning_customer=False).count()
        returning_count = appts_qs.filter(is_returning_customer=True).count()

        # Sales totals
        m_sales_qs = Sale.objects.filter(
            status=Sale.Status.COMPLETED,
            created_at__date__gte=m_start,
            created_at__date__lte=m_end,
        )
        if filter_branch:
            m_sales_qs = m_sales_qs.filter(branch=filter_branch)

        m_sales_agg = m_sales_qs.aggregate(
            gross_sales=Sum('subtotal'),
            net_sales=Sum('total')
        )

        m_refund_qs = Refund.objects.filter(
            status=Refund.Status.COMPLETED,
            created_at__date__gte=m_start,
            created_at__date__lte=m_end,
        )
        if filter_branch:
            m_refund_qs = m_refund_qs.filter(sale__branch=filter_branch)
        m_refund_total = m_refund_qs.aggregate(total=Sum('amount'))[
            'total'] or Decimal('0')

        m_gross = float(m_sales_agg['gross_sales'] or 0)
        m_net = float((m_sales_agg['net_sales']
                      or Decimal('0')) - m_refund_total)

        months_data.append({
            'month': m_date.strftime('%b'),
            'year': m_date.year,
            'new': new_count,
            'returning': returning_count,
            'gross': m_gross,
            'net': m_net,
        })

    # Current period new vs returning
    period_appts = Appointment.objects.filter(
        appointment_date__gte=date_from,
        appointment_date__lte=date_to,
    ).exclude(status='CANCELLED')
    if filter_branch:
        period_appts = period_appts.filter(branch=filter_branch)

    new_clients = period_appts.filter(is_returning_customer=False).count()
    returning_clients = period_appts.filter(is_returning_customer=True).count()

    # ── Branches for filter dropdown ──────────────────────────────────
    branches = Branch.objects.filter(is_active=True).order_by('name')

    context = {
        # Filters
        'branches': branches,
        'selected_branch': branch_id,
        'selected_period': period,
        'period_label': period_label,
        'date_from': date_from,
        'date_to': date_to,
        # Metric 1
        'total_patients': total_patients,
        'new_patients_period': new_patients_period,
        # Metric 2
        'gross_sales': gross_sales,
        'net_sales': net_sales,
        'total_discount': total_discount,
        'transaction_count': transaction_count,
        # Metric 3
        'new_clients': new_clients,
        'returning_clients': returning_clients,
        'months_data': json.dumps(months_data),
    }
    return render(request, 'reports/analytics_dashboard.html', context)


# =============================================================================
# Finance Dashboard
# =============================================================================

@login_required
@module_permission_required('reports', 'VIEW')
def finance_dashboard(request):
    """Main finance analytics dashboard."""
    branch = request.user.branch
    today = timezone.now().date()
    start_of_month = today.replace(day=1)
    start_of_week = today - timedelta(days=today.weekday())

    # Filter by branch for branch admins
    sales_qs = Sale.objects.filter(status=Sale.Status.COMPLETED)
    if request.user.is_module_branch_restricted('reports') and branch:
        sales_qs = sales_qs.filter(branch=branch)

    # Today's Sales
    today_sales = sales_qs.filter(created_at__date=today).aggregate(
        total=Sum('total'),
        count=Count('id')
    )

    # This Week's Sales
    week_sales = sales_qs.filter(created_at__date__gte=start_of_week).aggregate(
        total=Sum('total'),
        count=Count('id')
    )

    # This Month's Sales
    month_sales = sales_qs.filter(created_at__date__gte=start_of_month).aggregate(
        total=Sum('total'),
        count=Count('id')
    )

    # Sales by Day (last 30 days) for chart
    thirty_days_ago = today - timedelta(days=30)
    daily_sales = sales_qs.filter(
        created_at__date__gte=thirty_days_ago
    ).annotate(
        date=TruncDate('created_at')
    ).values('date').annotate(
        total=Sum('total'),
        count=Count('id')
    ).order_by('date')

    # Payment Methods Breakdown (this month)
    payment_methods = Payment.objects.filter(
        sale__status=Sale.Status.COMPLETED,
        sale__created_at__date__gte=start_of_month
    )
    if request.user.is_module_branch_restricted('reports') and branch:
        payment_methods = payment_methods.filter(sale__branch=branch)

    payment_breakdown = payment_methods.values('method').annotate(
        total=Sum('amount'),
        count=Count('id')
    ).order_by('-total')

    # Top Services (this month)
    top_services = SaleItem.objects.filter(
        sale__status=Sale.Status.COMPLETED,
        sale__created_at__date__gte=start_of_month,
        item_type='SERVICE'
    )
    if request.user.is_module_branch_restricted('reports') and branch:
        top_services = top_services.filter(sale__branch=branch)

    top_services = top_services.values('name').annotate(
        revenue=Sum(ExpressionWrapper(F('unit_price') *
                    F('quantity'), output_field=DecimalField())),
        count=Sum('quantity')
    ).order_by('-revenue')[:10]

    # Top Products (this month)
    top_products = SaleItem.objects.filter(
        sale__status=Sale.Status.COMPLETED,
        sale__created_at__date__gte=start_of_month,
        item_type__in=['PRODUCT', 'MEDICATION']
    )
    if request.user.is_module_branch_restricted('reports') and branch:
        top_products = top_products.filter(sale__branch=branch)

    top_products = top_products.values('name').annotate(
        revenue=Sum(ExpressionWrapper(F('unit_price') *
                    F('quantity'), output_field=DecimalField())),
        count=Sum('quantity')
    ).order_by('-revenue')[:10]

    # Prepare chart data
    chart_labels = []
    chart_data = []
    for day in daily_sales:
        chart_labels.append(day['date'].strftime('%b %d'))
        chart_data.append(float(day['total'] or 0))

    context = {
        'today_sales': today_sales,
        'week_sales': week_sales,
        'month_sales': month_sales,
        'payment_breakdown': payment_breakdown,
        'top_services': top_services,
        'top_products': top_products,
        'chart_labels': json.dumps(chart_labels),
        'chart_data': json.dumps(chart_data),
    }
    return render(request, 'reports/finance_dashboard.html', context)


# =============================================================================
# Daily Sales Report
# =============================================================================

@login_required
@module_permission_required('reports', 'VIEW')
def daily_sales_report(request):
    """Daily sales summary report."""
    branch = request.user.branch
    date_str = request.GET.get('date')

    if date_str:
        report_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    else:
        report_date = timezone.now().date()

    # Filter sales
    sales_qs = Sale.objects.filter(
        created_at__date=report_date,
        status=Sale.Status.COMPLETED
    )
    if request.user.is_module_branch_restricted('reports') and branch:
        sales_qs = sales_qs.filter(branch=branch)

    # Summary
    summary = sales_qs.aggregate(
        total_sales=Sum('total'),
        total_transactions=Count('id'),
        total_items=Count('items'),
        avg_transaction=Avg('total'),
    )

    # Calculate total discount amount: sum of (subtotal * discount_percent / 100)
    total_discount = Decimal('0')
    for sale in sales_qs:
        if sale.discount_percent > 0:
            total_discount = total_discount + \
                (sale.subtotal * sale.discount_percent /
                 Decimal('100')).quantize(Decimal('0.01'))
    summary['total_discount'] = total_discount

    # Payment breakdown
    payments = Payment.objects.filter(
        sale__in=sales_qs
    ).values('method').annotate(
        total=Sum('amount'),
        count=Count('id')
    )

    # Hourly breakdown
    hourly_sales = sales_qs.annotate(
        hour=ExtractHour('created_at')
    ).values('hour').annotate(
        total=Sum('total'),
        count=Count('id')
    ).order_by('hour')

    # Items sold
    items_sold = SaleItem.objects.filter(
        sale__in=sales_qs
    ).values('item_type', 'name').annotate(
        total_qty=Sum('quantity'),
        revenue=Sum(ExpressionWrapper(F('unit_price') *
                    F('quantity'), output_field=DecimalField()))
    ).order_by('-revenue')

    context = {
        'report_date': report_date,
        'summary': summary,
        'payments': payments,
        'hourly_sales': hourly_sales,
        'items_sold': items_sold,
        'sales': sales_qs.order_by('-created_at'),
    }
    return render(request, 'reports/daily_sales_report.html', context)


# =============================================================================
# Sales by Period Report
# =============================================================================

@login_required
@module_permission_required('reports', 'VIEW')
def sales_by_period(request):
    """Sales report filtered by date range, branch, category."""
    branch = request.user.branch

    # Get filter parameters
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    branch_id = request.GET.get('branch')
    category = request.GET.get('category')

    # Default to current month
    today = timezone.now().date()
    if not date_from:
        date_from = today.replace(day=1).strftime('%Y-%m-%d')
    if not date_to:
        date_to = today.strftime('%Y-%m-%d')

    # Build queryset
    sales_qs = Sale.objects.filter(
        status=Sale.Status.COMPLETED,
        created_at__date__gte=date_from,
        created_at__date__lte=date_to
    )

    # Apply branch filter
    if request.user.is_module_branch_restricted('reports') and branch:
        sales_qs = sales_qs.filter(branch=branch)
    elif branch_id:
        sales_qs = sales_qs.filter(branch_id=branch_id)

    # Summary
    summary = sales_qs.aggregate(
        total_sales=Sum('total'),
        total_transactions=Count('id'),
        avg_transaction=Avg('total'),
    )

    # Calculate total discount amount: sum of (subtotal * discount_percent / 100)
    total_discount = Decimal('0')
    for sale in sales_qs:
        if sale.discount_percent > 0:
            total_discount = total_discount + \
                (sale.subtotal * sale.discount_percent /
                 Decimal('100')).quantize(Decimal('0.01'))
    summary['total_discount'] = total_discount

    # Sales by branch
    sales_by_branch = sales_qs.values(
        'branch__name'
    ).annotate(
        total=Sum('total'),
        count=Count('id')
    ).order_by('-total')

    # Sales by day
    daily_breakdown = sales_qs.annotate(
        date=TruncDate('created_at')
    ).values('date').annotate(
        total=Sum('total'),
        count=Count('id')
    ).order_by('date')

    # Items breakdown by category
    items_qs = SaleItem.objects.filter(sale__in=sales_qs)
    if category and category != 'all':
        items_qs = items_qs.filter(item_type=category.upper())

    items_by_category = items_qs.values('item_type').annotate(
        revenue=Sum(ExpressionWrapper(F('unit_price') *
                    F('quantity'), output_field=DecimalField())),
        quantity=Sum('quantity')
    ).order_by('-revenue')

    # Get branches for filter dropdown
    branches = Branch.objects.filter(is_active=True)

    context = {
        'summary': summary,
        'sales_by_branch': sales_by_branch,
        'daily_breakdown': daily_breakdown,
        'items_by_category': items_by_category,
        'branches': branches,
        'date_from': date_from,
        'date_to': date_to,
        'selected_branch': branch_id,
        'selected_category': category,
    }
    return render(request, 'reports/sales_by_period.html', context)


# =============================================================================
# Operations Dashboard
# =============================================================================

@login_required
@module_permission_required('reports', 'VIEW')
def operations_dashboard(request):
    """Operations analytics dashboard."""
    branch = request.user.branch
    today = timezone.now().date()
    start_of_month = today.replace(day=1)

    # Appointments filter
    appointments_qs = Appointment.objects.all()
    if request.user.is_module_branch_restricted('reports') and branch:
        appointments_qs = appointments_qs.filter(branch=branch)

    # Today's appointments
    today_appointments = appointments_qs.filter(appointment_date=today)
    today_stats = {
        'total': today_appointments.count(),
        'pending': today_appointments.filter(status='PENDING').count(),
        'confirmed': today_appointments.filter(status='CONFIRMED').count(),
        'completed': today_appointments.filter(status='COMPLETED').count(),
        'cancelled': today_appointments.filter(status='CANCELLED').count(),
    }

    # Month appointments
    month_appointments = appointments_qs.filter(
        appointment_date__gte=start_of_month)
    month_stats = {
        'total': month_appointments.count(),
        'completed': month_appointments.filter(status='COMPLETED').count(),
        'cancelled': month_appointments.filter(status='CANCELLED').count(),
    }
    month_stats['completion_rate'] = (
        round(month_stats['completed'] / month_stats['total'] * 100, 1)
        if month_stats['total'] > 0 else 0
    )

    # Appointments by reason
    by_reason = month_appointments.values('reason_for_visit__name').annotate(
        count=Count('id')
    ).order_by('-count')
    by_reason = [
        {'reason': row['reason_for_visit__name']
            or 'Unspecified', 'count': row['count']}
        for row in by_reason
    ]

    # Appointments by branch (admin only)
    by_branch = None
    if not request.user.is_module_branch_restricted('reports'):
        by_branch = month_appointments.values('branch__name').annotate(
            count=Count('id')
        ).order_by('-count')

    # Inventory alerts
    inventory_qs = Product.objects.filter(is_available=True)
    if branch:
        inventory_qs = inventory_qs.filter(branch=branch)

    low_stock = inventory_qs.filter(
        stock_quantity__lte=F('min_stock_level'),
        stock_quantity__gt=0
    ).count()
    out_of_stock = inventory_qs.filter(stock_quantity=0).count()

    # Expiring soon (30 days)
    expiring_date = today + timedelta(days=30)
    expiring_soon = inventory_qs.filter(
        expiration_date__lte=expiring_date,
        expiration_date__gte=today
    ).count()

    # Patient stats
    pets_qs = Pet.objects.filter(is_active=True)
    total_patients = pets_qs.count()
    new_patients_month = pets_qs.filter(
        created_at__date__gte=start_of_month).count()

    context = {
        'today_stats': today_stats,
        'month_stats': month_stats,
        'by_reason': by_reason,
        'by_branch': by_branch,
        'low_stock': low_stock,
        'out_of_stock': out_of_stock,
        'expiring_soon': expiring_soon,
        'total_patients': total_patients,
        'new_patients_month': new_patients_month,
    }
    return render(request, 'reports/operations_dashboard.html', context)


# =============================================================================
# Customer Analytics
# =============================================================================

@login_required
@module_permission_required('reports', 'VIEW')
def customer_analytics(request):
    """Customer and patient analytics."""
    branch = request.user.branch
    today = timezone.now().date()
    start_of_month = today.replace(day=1)

    # Sales filter
    sales_qs = Sale.objects.filter(status=Sale.Status.COMPLETED)
    if request.user.is_module_branch_restricted('reports') and branch:
        sales_qs = sales_qs.filter(branch=branch)

    # Top customers by spending (this month)
    top_customers = sales_qs.filter(
        created_at__date__gte=start_of_month,
        customer__isnull=False
    ).values(
        'customer__id',
        'customer__first_name',
        'customer__last_name',
        'customer__email'
    ).annotate(
        total_spent=Sum('total'),
        visit_count=Count('id')
    ).order_by('-total_spent')[:10]

    # Customer type breakdown
    customer_breakdown = sales_qs.filter(
        created_at__date__gte=start_of_month
    ).values('customer_type').annotate(
        count=Count('id'),
        total=Sum('total')
    )

    # New vs returning (appointments)
    appointments_qs = Appointment.objects.filter(
        appointment_date__gte=start_of_month
    )
    if branch:
        appointments_qs = appointments_qs.filter(branch=branch)

    new_customers = appointments_qs.filter(is_returning_customer=False).count()
    returning_customers = appointments_qs.filter(
        is_returning_customer=True).count()

    # Species breakdown
    pets_qs = Pet.objects.filter(is_active=True)
    species_breakdown = pets_qs.values('species').annotate(
        count=Count('id')
    ).order_by('-count')[:10]

    context = {
        'top_customers': top_customers,
        'customer_breakdown': customer_breakdown,
        'new_customers': new_customers,
        'returning_customers': returning_customers,
        'species_breakdown': species_breakdown,
    }
    return render(request, 'reports/customer_analytics.html', context)


# =============================================================================
# Export Functions
# =============================================================================

@login_required
@module_permission_required('reports', 'MANAGE')
def export_sales_csv(request):
    """Export sales data to CSV."""
    import csv

    branch = request.user.branch
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')

    # Default to current month
    today = timezone.now().date()
    if not date_from:
        date_from = today.replace(day=1).strftime('%Y-%m-%d')
    if not date_to:
        date_to = today.strftime('%Y-%m-%d')

    # Build queryset
    sales_qs = Sale.objects.filter(
        status=Sale.Status.COMPLETED,
        created_at__date__gte=date_from,
        created_at__date__lte=date_to
    )
    if request.user.is_module_branch_restricted('reports') and branch:
        sales_qs = sales_qs.filter(branch=branch)

    # Create response
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="sales_{date_from}_to_{date_to}.csv"'

    writer = csv.writer(response)
    writer.writerow([
        'Transaction ID', 'Date', 'Time', 'Branch', 'Customer',
        'Subtotal', 'Discount', 'Total', 'Payment Method', 'Cashier'
    ])

    for sale in sales_qs.select_related('branch', 'cashier').order_by('created_at'):
        payment_methods = ', '.join(
            [p.get_method_display() for p in sale.payments.all()])
        # Calculate actual discount amount from percentage
        discount_amt = (sale.subtotal * sale.discount_percent / Decimal('100')).quantize(
            Decimal('0.01')) if sale.discount_percent > 0 else Decimal('0.00')
        writer.writerow([
            sale.transaction_id,
            sale.created_at.strftime('%Y-%m-%d'),
            sale.created_at.strftime('%H:%M'),
            sale.branch.name,
            sale.customer_display_name,
            sale.subtotal,
            discount_amt,
            sale.total,
            payment_methods,
            sale.cashier.get_full_name() if sale.cashier else '-'
        ])

    return response


@login_required
@module_permission_required('reports', 'MANAGE')
def export_daily_report_csv(request):
    """Export daily sales report to CSV."""
    import csv

    branch = request.user.branch
    date_str = request.GET.get('date')

    if date_str:
        report_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    else:
        report_date = timezone.now().date()

    sales_qs = Sale.objects.filter(
        created_at__date=report_date,
        status=Sale.Status.COMPLETED
    )
    if request.user.is_module_branch_restricted('reports') and branch:
        sales_qs = sales_qs.filter(branch=branch)

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="daily_report_{report_date}.csv"'

    writer = csv.writer(response)

    # Summary section
    summary = sales_qs.aggregate(
        total_sales=Sum('total'),
        total_transactions=Count('id'),
    )
    writer.writerow(['Daily Sales Report', report_date])
    writer.writerow([])
    writer.writerow(['Summary'])
    writer.writerow(['Total Sales', summary['total_sales'] or 0])
    writer.writerow(['Total Transactions', summary['total_transactions'] or 0])
    writer.writerow([])

    # Transactions
    writer.writerow(['Transactions'])
    writer.writerow(['Time', 'Transaction ID', 'Customer', 'Total', 'Payment'])

    for sale in sales_qs.order_by('created_at'):
        payment_methods = ', '.join(
            [p.get_method_display() for p in sale.payments.all()])
        writer.writerow([
            sale.created_at.strftime('%H:%M'),
            sale.transaction_id,
            sale.customer_display_name,
            sale.total,
            payment_methods
        ])

    return response


# =============================================================================
# FINANCE: Gross Profit Report
# =============================================================================

@login_required
@module_permission_required('reports', 'VIEW')
def gross_profit_report(request):
    """Revenue minus cost per item — profit margins."""
    branch = request.user.branch
    today = timezone.now().date()
    date_from = request.GET.get(
        'date_from', today.replace(day=1).strftime('%Y-%m-%d'))
    date_to = request.GET.get('date_to', today.strftime('%Y-%m-%d'))

    items_qs = SaleItem.objects.filter(
        sale__status=Sale.Status.COMPLETED,
        sale__created_at__date__gte=date_from,
        sale__created_at__date__lte=date_to,
    )
    if request.user.is_module_branch_restricted('reports') and branch:
        items_qs = items_qs.filter(sale__branch=branch)

    profit_items = []
    for item in items_qs.select_related('product', 'service'):
        revenue = item.unit_price * item.quantity
        if item.product:
            cost = (item.product.unit_cost or Decimal('0')) * item.quantity
        else:
            cost = Decimal('0')
        profit = revenue - cost
        margin = round((profit / revenue) * 100, 1) if revenue else 0
        profit_items.append({
            'name': item.name,
            'item_type': item.item_type,
            'quantity': item.quantity,
            'revenue': revenue,
            'cost': cost,
            'profit': profit,
            'margin': margin,
        })

    total_revenue = sum(i['revenue'] for i in profit_items)
    total_cost = sum(i['cost'] for i in profit_items)
    total_profit = total_revenue - total_cost
    overall_margin = round(float(total_profit / total_revenue)
                           * 100, 1) if total_revenue else 0

    by_type: dict = {}
    for i in profit_items:
        t = i['item_type']
        if t not in by_type:
            by_type[t] = {'revenue': Decimal('0'), 'cost': Decimal(
                '0'), 'profit': Decimal('0'), 'count': 0}
        by_type[t]['revenue'] = by_type[t]['revenue'] + i['revenue']
        by_type[t]['cost'] = by_type[t]['cost'] + i['cost']
        by_type[t]['profit'] = by_type[t]['profit'] + i['profit']
        by_type[t]['count'] = by_type[t]['count'] + i['quantity']
    by_type_list = [{'type': k, **v, 'margin': round(float(
        v['profit'] / v['revenue']) * 100, 1) if v['revenue'] else 0} for k, v in by_type.items()]

    context = {
        'profit_items': profit_items,
        'total_revenue': total_revenue,
        'total_cost': total_cost,
        'total_profit': total_profit,
        'overall_margin': overall_margin,
        'by_type_list': by_type_list,
        'date_from': date_from,
        'date_to': date_to,
    }
    return render(request, 'reports/gross_profit_report.html', context)


# =============================================================================
# FINANCE: Discount Report
# =============================================================================

@login_required
@module_permission_required('reports', 'VIEW')
def discount_report(request):
    """Discounts given — total discounts, percentage of sales."""
    branch = request.user.branch
    today = timezone.now().date()
    date_from = request.GET.get(
        'date_from', today.replace(day=1).strftime('%Y-%m-%d'))
    date_to = request.GET.get('date_to', today.strftime('%Y-%m-%d'))

    sales_qs = Sale.objects.filter(
        status=Sale.Status.COMPLETED,
        created_at__date__gte=date_from,
        created_at__date__lte=date_to,
        discount_percent__gt=0,
    )
    if request.user.is_module_branch_restricted('reports') and branch:
        sales_qs = sales_qs.filter(branch=branch)

    all_sales = Sale.objects.filter(
        status=Sale.Status.COMPLETED,
        created_at__date__gte=date_from,
        created_at__date__lte=date_to,
    )
    if request.user.is_module_branch_restricted('reports') and branch:
        all_sales = all_sales.filter(branch=branch)

    total_sales_revenue = all_sales.aggregate(total=Sum('total'))[
        'total'] or Decimal('0')

    # Calculate total discounts and averages
    total_discounts = Decimal('0')
    discount_count = 0
    for sale in sales_qs:
        if sale.discount_percent > 0:
            total_discounts += (sale.subtotal * sale.discount_percent /
                                Decimal('100')).quantize(Decimal('0.01'))
            discount_count += 1

    avg_discount = total_discounts / \
        discount_count if discount_count > 0 else Decimal('0')

    summary = {
        'total_discounts': total_discounts,
        'discount_count': discount_count,
        'avg_discount': avg_discount,
    }
    pct_of_sales = round(float(
        (total_discounts / total_sales_revenue) * 100), 1) if total_sales_revenue else 0

    discounted_sales = sales_qs.select_related(
        'branch', 'cashier').order_by('-created_at')[:50]

    context = {
        'summary': summary,
        'pct_of_sales': pct_of_sales,
        'total_sales_revenue': total_sales_revenue,
        'discounted_sales': discounted_sales,
        'date_from': date_from,
        'date_to': date_to,
    }
    return render(request, 'reports/discount_report.html', context)


# =============================================================================
# FINANCE: Refund Report
# =============================================================================

@login_required
@module_permission_required('reports', 'VIEW')
def refund_report(request):
    """Voided/refunded sales — reasons, amounts."""
    branch = request.user.branch
    today = timezone.now().date()
    date_from = request.GET.get(
        'date_from', today.replace(day=1).strftime('%Y-%m-%d'))
    date_to = request.GET.get('date_to', today.strftime('%Y-%m-%d'))

    refunds_qs = Refund.objects.filter(
        created_at__date__gte=date_from,
        created_at__date__lte=date_to,
    )
    if request.user.is_module_branch_restricted('reports') and branch:
        refunds_qs = refunds_qs.filter(sale__branch=branch)

    voided_qs = Sale.objects.filter(
        status=Sale.Status.VOIDED,
        updated_at__date__gte=date_from,
        updated_at__date__lte=date_to,
    )
    if request.user.is_module_branch_restricted('reports') and branch:
        voided_qs = voided_qs.filter(branch=branch)

    refund_summary = refunds_qs.aggregate(
        total_refunds=Sum('amount'),
        refund_count=Count('id'),
    )
    by_status = refunds_qs.values('status').annotate(
        count=Count('id'), total=Sum('amount')).order_by('-total')

    void_summary = voided_qs.aggregate(
        total_voided=Sum('total'), void_count=Count('id'))

    context = {
        'refund_summary': refund_summary,
        'void_summary': void_summary,
        'refunds': refunds_qs.select_related('sale', 'requested_by').order_by('-created_at')[:50],
        'voided_sales': voided_qs.select_related('branch', 'voided_by').order_by('-updated_at')[:50],
        'by_status': by_status,
        'date_from': date_from,
        'date_to': date_to,
    }
    return render(request, 'reports/refund_report.html', context)


# =============================================================================
# APPOINTMENT REPORTS
# =============================================================================

@login_required
@module_permission_required('reports', 'VIEW')
def appointment_reports(request):
    """Comprehensive appointment analytics."""
    branch = request.user.branch
    today = timezone.now().date()
    date_from = request.GET.get(
        'date_from', today.replace(day=1).strftime('%Y-%m-%d'))
    date_to = request.GET.get('date_to', today.strftime('%Y-%m-%d'))

    appts_qs = Appointment.objects.filter(
        appointment_date__gte=date_from,
        appointment_date__lte=date_to,
    )
    if request.user.is_module_branch_restricted('reports') and branch:
        appts_qs = appts_qs.filter(branch=branch)

    total = appts_qs.count()

    by_status = appts_qs.values('status').annotate(
        count=Count('id')).order_by('-count')
    by_branch = appts_qs.values('branch__name').annotate(
        count=Count('id')).order_by('-count')
    by_vet = appts_qs.filter(preferred_vet__isnull=False).values(
        'preferred_vet__first_name', 'preferred_vet__last_name'
    ).annotate(count=Count('id')).order_by('-count')
    by_reason = appts_qs.values('reason_for_visit__name').annotate(
        count=Count('id')).order_by('-count')
    by_reason = [
        {'reason': row['reason_for_visit__name']
            or 'Unspecified', 'count': row['count']}
        for row in by_reason
    ]
    by_source = appts_qs.values('source').annotate(
        count=Count('id')).order_by('-count')

    cancelled = appts_qs.filter(status='CANCELLED').count()
    completed = appts_qs.filter(status='COMPLETED').count()
    no_show_rate = round(cancelled / total * 100, 1) if total > 0 else 0

    with_sale = appts_qs.filter(sale__isnull=False).count()
    conversion_rate = round(with_sale / total * 100, 1) if total > 0 else 0
    conversion_revenue = appts_qs.filter(sale__isnull=False).aggregate(
        total=Sum('sale__total'))['total'] or Decimal('0')

    peak_hours = appts_qs.values('appointment_time__hour').annotate(
        count=Count('id')
    ).order_by('appointment_time__hour')

    peak_days = appts_qs.annotate(
        day=TruncDate('appointment_date')
    ).values('day').annotate(count=Count('id')).order_by('day')

    context = {
        'total': total, 'completed': completed, 'cancelled': cancelled,
        'by_status': by_status, 'by_branch': by_branch, 'by_vet': by_vet,
        'by_reason': by_reason, 'by_source': by_source,
        'no_show_rate': no_show_rate, 'conversion_rate': conversion_rate,
        'conversion_revenue': conversion_revenue, 'with_sale': with_sale,
        'peak_hours': peak_hours, 'peak_days': peak_days,
        'date_from': date_from, 'date_to': date_to,
    }
    return render(request, 'reports/appointment_reports.html', context)


# =============================================================================
# INVENTORY REPORTS
# =============================================================================

@login_required
@module_permission_required('reports', 'VIEW')
def inventory_reports(request):
    """Comprehensive inventory analytics."""
    branch = request.user.branch
    today = timezone.now().date()

    inventory_qs = Product.objects.filter(is_available=True)
    if request.user.is_module_branch_restricted('reports') and branch:
        inventory_qs = inventory_qs.filter(branch=branch)

    total_products = inventory_qs.count()
    total_value = inventory_qs.aggregate(
        val=Sum(ExpressionWrapper(F('stock_quantity') *
                F('unit_cost'), output_field=DecimalField()))
    )['val'] or Decimal('0')

    low_stock_items = inventory_qs.filter(stock_quantity__lte=F(
        'min_stock_level'), stock_quantity__gt=0).order_by('stock_quantity')
    out_of_stock_items = inventory_qs.filter(stock_quantity=0)
    expiring_date = today + timedelta(days=30)
    expiring_items = inventory_qs.filter(
        expiration_date__lte=expiring_date, expiration_date__gte=today).order_by('expiration_date')

    thirty_days_ago = today - timedelta(days=30)
    movements_qs = StockAdjustment.objects.filter(date__gte=thirty_days_ago)
    if request.user.is_module_branch_restricted('reports') and branch:
        movements_qs = movements_qs.filter(branch=branch)
    recent_movements = movements_qs.select_related(
        'product', 'branch').order_by('-date', '-pk')[:50]

    movement_by_type = movements_qs.values('adjustment_type').annotate(
        count=Count('id'), total_qty=Sum('quantity')
    ).order_by('-total_qty')

    top_sellers = SaleItem.objects.filter(
        sale__status=Sale.Status.COMPLETED,
        sale__created_at__date__gte=thirty_days_ago,
        item_type__in=['PRODUCT', 'MEDICATION'],
        product__isnull=False,
    )
    if request.user.is_module_branch_restricted('reports') and branch:
        top_sellers = top_sellers.filter(sale__branch=branch)
    top_sellers = top_sellers.values('product__id', 'product__name').annotate(
        units_sold=Sum('quantity'),
        revenue=Sum(ExpressionWrapper(F('unit_price') *
                    F('quantity'), output_field=DecimalField()))
    ).order_by('-units_sold')[:20]

    sixty_days_ago = today - timedelta(days=60)
    sold_product_ids = SaleItem.objects.filter(
        sale__status=Sale.Status.COMPLETED,
        sale__created_at__date__gte=sixty_days_ago,
        product__isnull=False,
    ).values_list('product_id', flat=True).distinct()
    dead_stock = inventory_qs.filter(
        item_type__in=['Product', 'Medication'],
        stock_quantity__gt=0,
    ).exclude(pk__in=sold_product_ids).order_by('-stock_quantity')

    context = {
        'total_products': total_products, 'total_value': total_value,
        'low_stock_items': low_stock_items, 'out_of_stock_items': out_of_stock_items,
        'expiring_items': expiring_items, 'recent_movements': recent_movements,
        'movement_by_type': movement_by_type, 'top_sellers': top_sellers,
        'dead_stock': dead_stock,
    }
    return render(request, 'reports/inventory_reports.html', context)


# =============================================================================
# PATIENT REPORTS
# =============================================================================

@login_required
@module_permission_required('reports', 'VIEW')
def patient_reports(request):
    """Patient analytics — census, treatments, follow-ups, critical cases."""
    today = timezone.now().date()
    start_of_month = today.replace(day=1)

    pets_qs = Pet.objects.filter(is_active=True)
    total_patients = pets_qs.count()
    by_species = pets_qs.values('species').annotate(
        count=Count('id')).order_by('-count')
    new_this_month = pets_qs.filter(
        created_at__date__gte=start_of_month).count()
    by_status = pets_qs.values('status').annotate(
        count=Count('id')).order_by('-count')
    critical_pets = pets_qs.filter(status='CRITICAL').select_related('owner')

    entries_qs = RecordEntry.objects.filter(date_recorded__gte=start_of_month)
    treatments_count = entries_qs.count()
    by_action = entries_qs.values('action_required').annotate(
        count=Count('id')).order_by('-count')
    by_vet = entries_qs.filter(vet__isnull=False).values(
        'vet__first_name', 'vet__last_name'
    ).annotate(count=Count('id')).order_by('-count')

    past_followups = RecordEntry.objects.filter(
        ff_up__isnull=False, ff_up__lt=today, ff_up__gte=start_of_month,
    )
    total_followups = past_followups.count()
    completed_followups = 0
    for entry in past_followups.select_related('record'):
        has_followup = RecordEntry.objects.filter(
            record=entry.record, date_recorded__gte=entry.ff_up
        ).exclude(pk=entry.pk).exists()
        if has_followup:
            completed_followups += 1
    followup_rate = round(float(
        completed_followups / total_followups) * 100, 1) if total_followups > 0 else 0

    upcoming_followups = RecordEntry.objects.filter(
        ff_up__gte=today, ff_up__lte=today + timedelta(days=7),
    ).select_related('record__pet', 'vet').order_by('ff_up')[:20]

    context = {
        'total_patients': total_patients, 'new_this_month': new_this_month,
        'by_species': by_species, 'by_status': by_status, 'critical_pets': critical_pets,
        'treatments_count': treatments_count, 'by_action': by_action, 'by_vet': by_vet,
        'total_followups': total_followups, 'completed_followups': completed_followups,
        'followup_rate': followup_rate, 'upcoming_followups': upcoming_followups,
    }
    return render(request, 'reports/patient_reports.html', context)


# =============================================================================
# CUSTOMER: Customer List & Lifetime Value
# =============================================================================

@login_required
@module_permission_required('reports', 'VIEW')
def customer_list_report(request):
    """Customer list with lifetime value and purchase history."""
    branch = request.user.branch
    search = request.GET.get('q', '')

    # Get pet owners (not staff or no role)
    customers = User.objects.filter(
        is_active=True
    ).filter(
        Q(assigned_role__is_staff_role=False) | Q(assigned_role__isnull=True)
    )
    if search:
        customers = customers.filter(
            Q(first_name__icontains=search) |
            Q(last_name__icontains=search) |
            Q(email__icontains=search)
        )

    sales_filter = Q(purchases__status=Sale.Status.COMPLETED)
    if request.user.is_module_branch_restricted('reports') and branch:
        sales_filter &= Q(purchases__branch=branch)

    customers = customers.annotate(
        total_spent=Sum('purchases__total', filter=sales_filter),
        visit_count=Count('purchases', filter=sales_filter),
    ).order_by('-total_spent')

    total_customers = customers.count()
    avg_ltv = customers.aggregate(avg=Avg('total_spent'))['avg'] or 0

    from django.core.paginator import Paginator
    paginator = Paginator(customers, 25)
    page = request.GET.get('page', 1)
    customers_page = paginator.get_page(page)

    context = {
        'customers': customers_page,
        'total_customers': total_customers,
        'avg_ltv': avg_ltv,
        'search': search,
    }
    return render(request, 'reports/customer_list_report.html', context)


# =============================================================================
# Analytics Dashboard Excel Export
# =============================================================================

@login_required
@module_permission_required('reports', 'MANAGE')
def export_analytics_excel(request):
    """Export analytics dashboard data to Excel (.xlsx) format divided by branches."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from io import BytesIO

    user_branch = request.user.branch
    today = timezone.now().date()

    # ── Filters ─────────────────────────
    period = request.GET.get('period', 'monthly')

    if period == 'daily':
        date_from = today
        date_to = today
        period_label = today.strftime('%B %d, %Y')
    elif period == 'weekly':
        date_from = today - timedelta(days=today.weekday())
        date_to = date_from + timedelta(days=6)
        period_label = f"{date_from.strftime('%b %d')} – {date_to.strftime('%b %d, %Y')}"
    else:
        date_from = today.replace(day=1)
        _, last_day = monthrange(today.year, today.month)
        date_to = today.replace(day=last_day)
        period_label = today.strftime('%B %Y')

    branches = Branch.objects.filter(is_active=True).order_by('name')
    if request.user.is_module_branch_restricted('reports') and user_branch:
        branches = branches.filter(id=user_branch.id)

    wb = Workbook()

    # Styles
    header_font = Font(name='Calibri', bold=True, size=12, color='FFFFFF')
    header_fill = PatternFill(start_color='009688',
                              end_color='009688', fill_type='solid')
    label_font = Font(name='Calibri', bold=True, size=11)
    value_font = Font(name='Calibri', size=11)
    branch_font = Font(name='Calibri', bold=True, size=14, color='009688')
    money_format = '#,##0.00'
    thin_border = Border(
        left=Side(style='thin'),
        right=Side(style='thin'),
        top=Side(style='thin'),
        bottom=Side(style='thin')
    )

    ws = wb.active
    ws.title = 'Analytics Summary'
    ws.column_dimensions['A'].width = 30
    ws.column_dimensions['B'].width = 25
    ws.column_dimensions['C'].width = 20
    ws.column_dimensions['D'].width = 20
    ws.column_dimensions['E'].width = 20

    ws.append(['FMH Animal Clinic — Analytics Report'])
    ws.merge_cells('A1:C1')
    ws['A1'].font = Font(name='Calibri', bold=True, size=16)

    ws.append([f'Period: {period_label}'])
    ws['A2'].font = Font(name='Calibri', italic=True, size=11)
    ws.append([f'Generated: {timezone.now().strftime("%B %d, %Y %I:%M %p")}'])
    ws.append([])

    current_row = 5
    has_data = False

    for current_branch in branches:
        has_data = True
        # ── Gather data ───────────────────────────────────────────────────
        pets_qs = Pet.objects.filter(is_active=True)
        total_patients = pets_qs.count()
        new_patients_period = pets_qs.filter(
            created_at__date__gte=date_from,
            created_at__date__lte=date_to
        ).count()

        sales_qs = Sale.objects.filter(
            status=Sale.Status.COMPLETED,
            created_at__date__gte=date_from,
            created_at__date__lte=date_to,
            branch=current_branch
        )

        sales_agg = sales_qs.aggregate(
            gross_sales=Sum('subtotal'),
            net_sales=Sum('total'),
            transaction_count=Count('id'),
        )
        gross_sales = sales_agg['gross_sales'] or Decimal('0')
        net_sales = sales_agg['net_sales'] or Decimal('0')
        total_discount = Decimal('0')
        for sale in sales_qs:
            if sale.discount_percent > 0:
                total_discount += (sale.subtotal * sale.discount_percent /
                                   Decimal('100')).quantize(Decimal('0.01'))
        transaction_count = sales_agg['transaction_count'] or 0

        refund_qs = Refund.objects.filter(
            status=Refund.Status.COMPLETED,
            created_at__date__gte=date_from,
            created_at__date__lte=date_to,
            sale__branch=current_branch
        )
        total_refunds = refund_qs.aggregate(total=Sum('amount'))[
            'total'] or Decimal('0')
        net_sales -= total_refunds

        period_appts = Appointment.objects.filter(
            appointment_date__gte=date_from,
            appointment_date__lte=date_to,
            branch=current_branch
        ).exclude(status='CANCELLED')

        new_clients = period_appts.filter(is_returning_customer=False).count()
        returning_clients = period_appts.filter(
            is_returning_customer=True).count()

        # 12-month data
        months_data = []
        for i in range(11, -1, -1):
            m_date = today.replace(day=1)
            for _ in range(i):
                m_date = (m_date - timedelta(days=1)).replace(day=1)

            m_start = m_date
            _, m_last = monthrange(m_date.year, m_date.month)
            m_end = m_date.replace(day=m_last)

            appts_qs = Appointment.objects.filter(
                appointment_date__gte=m_start,
                appointment_date__lte=m_end,
                branch=current_branch
            ).exclude(status='CANCELLED')

            new_count = appts_qs.filter(is_returning_customer=False).count()
            returning_count = appts_qs.filter(
                is_returning_customer=True).count()

            m_sales_qs = Sale.objects.filter(
                status=Sale.Status.COMPLETED,
                created_at__date__gte=m_start,
                created_at__date__lte=m_end,
                branch=current_branch
            )

            m_sales_agg = m_sales_qs.aggregate(
                gross_sales=Sum('subtotal'),
                net_sales=Sum('total')
            )

            m_refund_qs = Refund.objects.filter(
                status=Refund.Status.COMPLETED,
                created_at__date__gte=m_start,
                created_at__date__lte=m_end,
                sale__branch=current_branch
            )
            m_refund_total = m_refund_qs.aggregate(total=Sum('amount'))[
                'total'] or Decimal('0')

            months_data.append({
                'month': m_date.strftime('%B %Y'),
                'new': new_count,
                'returning': returning_count,
                'gross': float(m_sales_agg['gross_sales'] or 0),
                'net': float((m_sales_agg['net_sales'] or Decimal('0')) - m_refund_total),
            })

        # Write Branch Header
        cell = ws.cell(row=current_row, column=1,
                       value=f"Branch: {current_branch.name}")
        cell.font = branch_font
        current_row += 1

        # Summary Metrics
        metrics = [
            ('Metric', 'Value'),
            ('Total Patients', total_patients),
            ('New Patients (period)', new_patients_period),
            ('Gross Sales', float(gross_sales)),
            ('Net Sales', float(net_sales)),
            ('Total Discounts', float(total_discount)),
            ('Transactions', transaction_count),
            ('New Clients (period)', new_clients),
            ('Returning Clients (period)', returning_clients),
        ]

        # append metrics table
        for r_idx, (m_label, m_val) in enumerate(metrics):
            cell_label = ws.cell(row=current_row, column=1, value=m_label)
            cell_val = ws.cell(row=current_row, column=2, value=m_val)

            if r_idx == 0:
                cell_label.font = header_font
                cell_label.fill = header_fill
                cell_val.font = header_font
                cell_val.fill = header_fill
            else:
                cell_label.font = label_font
                cell_val.font = value_font
                if isinstance(m_val, float):
                    cell_val.number_format = money_format

            cell_label.border = thin_border
            cell_val.border = thin_border
            current_row += 1

        current_row += 1  # Empty row

        # Write Monthly Trends
        headers = ['Month', 'New Clients',
                   'Returning Clients', 'Gross Sales', 'Net Sales']
        for col_idx, header in enumerate(headers, start=1):
            cell = ws.cell(row=current_row, column=col_idx, value=header)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal='center')
            cell.border = thin_border
        current_row += 1

        for m in months_data:
            ws.cell(row=current_row, column=1,
                    value=m['month']).border = thin_border
            ws.cell(row=current_row, column=2,
                    value=m['new']).border = thin_border
            ws.cell(row=current_row, column=3,
                    value=m['returning']).border = thin_border

            gross_cell = ws.cell(row=current_row, column=4, value=m['gross'])
            gross_cell.number_format = money_format
            gross_cell.border = thin_border

            net_cell = ws.cell(row=current_row, column=5, value=m['net'])
            net_cell.number_format = money_format
            net_cell.border = thin_border

            current_row += 1

        current_row += 2  # extra space before next branch

    if not has_data:
        ws.append(["No data to display."])

    # ── Save and return ───────────────────────────────────────────────
    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    filename = f'analytics_{period}_{date_from}_to_{date_to}.xlsx'
    response = HttpResponse(
        buffer.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response
