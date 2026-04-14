"""Views for the billing app — clinic services and owner statement modules.
# pylint: disable=no-member
"""
from django.core.paginator import Paginator
from django.urls import reverse_lazy
from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import CreateView, UpdateView
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.contrib import messages
from django.db.models import Q

from accounts.decorators import module_permission_required
from accounts.decorators import ModulePermissionMixin
from .models import Service, CustomerStatement
from .forms import ServiceForm


@login_required
@module_permission_required('clinic_services', 'VIEW')
def service_list(request):
    """View for listing all clinic services with filtering and search."""
    services = Service.objects.all()

    # Filter by status (active/inactive)
    status = request.GET.get('status')
    if status == 'active':
        services = services.filter(active=True)
    elif status == 'inactive':
        services = services.filter(active=False)

    # Filter by category
    category = request.GET.get('category')
    if category:
        services = services.filter(category=category)

    # Search by name
    search = request.GET.get('q')
    if search:
        services = services.filter(
            Q(name__icontains=search) |
            Q(category__icontains=search) |
            Q(description__icontains=search)
        )

    # Get all categories for dropdown (use set to ensure distinctness regardless of default model ordering)
    all_categories = set(Service.objects.values_list('category', flat=True))
    categories = sorted([c for c in all_categories if c])

    # Order by category and name to match POS layout instead of -created_at
    services = services.order_by('category', 'name')

    # Check permissions for CRUD buttons
    can_create = request.user.has_module_permission(
        'clinic_services', 'CREATE')
    can_edit = request.user.has_module_permission('clinic_services', 'EDIT')
    can_delete = request.user.has_module_permission(
        'clinic_services', 'DELETE')

    # Check if user is branch-restricted
    is_branch_restricted = request.user.is_module_branch_restricted(
        'clinic_services')

    # Branch filtering
    if is_branch_restricted and request.user.branch:
        services = services.filter(
            Q(branch=request.user.branch) | Q(branch__isnull=True))
    else:
        branch_id = request.GET.get('branch')
        if branch_id:
            services = services.filter(
                Q(branch_id=branch_id) | Q(branch__isnull=True))

    from branches.models import Branch
    all_branches = Branch.objects.all()

    # Create full list of services for the Javascript live search
    import json
    all_services_list = list(services.values('name', 'category', 'active'))
    for s in all_services_list:
        s['status'] = 'Active' if s['active'] else 'Inactive'
        s['category'] = s['category'] or '-'
        del s['active']
    all_services_json = json.dumps(all_services_list)

    # Pagination - limit to 50 as requested
    page_number = request.GET.get('page', 1)
    paginator = Paginator(services, 50)
    page_obj = paginator.get_page(page_number)

    # Next URL query string for preserving filters on edit/delete
    from urllib.parse import quote
    next_url_qs = f"?next={quote(request.get_full_path())}"

    context = {
        'items': page_obj,
        'page_obj': page_obj,
        'categories': categories,
        'branches': all_branches,
        'status_choices': [('active', 'Active'), ('inactive', 'Inactive')],
        'can_create': can_create,
        'can_edit': can_edit,
        'can_delete': can_delete,
        'is_branch_restricted': is_branch_restricted,
        'all_services_json': all_services_json,
        'next_url_qs': next_url_qs,
    }
    return render(request, 'billing/services.html', context)


class ServiceCreateView(ModulePermissionMixin, LoginRequiredMixin, SuccessMessageMixin, CreateView):
    """View for creating a new clinic service."""
    model = Service
    form_class = ServiceForm
    template_name = 'billing/service_form.html'
    module_code = 'clinic_services'
    permission_type = 'CREATE'
    success_message = "Service successfully created!"

    def get_success_url(self):
        next_url = self.request.GET.get('next')
        if next_url:
            return next_url
        return reverse_lazy('billing:billable_items')


class ServiceUpdateView(ModulePermissionMixin, LoginRequiredMixin, SuccessMessageMixin, UpdateView):
    """View for updating an existing clinic service."""
    model = Service
    form_class = ServiceForm
    template_name = 'billing/service_form.html'
    module_code = 'clinic_services'
    permission_type = 'EDIT'
    success_message = "Service successfully updated!"

    def get_success_url(self):
        next_url = self.request.GET.get('next')
        if next_url:
            return next_url
        return reverse_lazy('billing:billable_items')


@login_required
@module_permission_required('clinic_services', 'DELETE')
def service_delete(request, pk):
    """View for deleting a clinic service."""
    item = get_object_or_404(Service, pk=pk)
    if request.method == 'POST':
        item.delete()
        messages.success(request, "Service successfully deleted!")
        next_url = request.GET.get('next')
        if next_url:
            return redirect(next_url)
    return redirect('billing:billable_items')


@login_required
def my_statements(request):
    """Pet owner statement module: released statements tied to current user."""
    statements_list = (
        CustomerStatement.objects
        .filter(customer=request.user, status__in=['RELEASED', 'SENT'])
        .select_related('branch', 'sale')
        .order_by('-created_at')
    )

    paginator = Paginator(statements_list, 9)
    page_number = request.GET.get('page')
    statements = paginator.get_page(page_number)

    return render(request, 'billing/my_statements.html', {
        'statements': statements,
        'page_obj': statements
    })


@login_required
def my_statement_detail(request, pk):
    """Pet owner statement detail with printable format."""
    statement = get_object_or_404(
        CustomerStatement.objects.select_related('branch', 'sale', 'customer'),
        pk=pk,
        customer=request.user,
        status__in=['RELEASED', 'SENT'],
    )

    if request.GET.get('format') == 'print':
        return render(
            request,
            'billing/my_statement_print.html',
            {
                'statement': statement,
            },
        )

    return render(request, 'billing/my_statement_detail.html', {'statement': statement})
