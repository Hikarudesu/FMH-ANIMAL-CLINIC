from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.db import transaction
from django.urls import reverse
from django.views.decorators.http import require_POST

from accounts.decorators import module_permission_required
from employees.models import RecurringSchedule, StaffMember, VetSchedule
from .models import Branch
from .forms import BranchForm


@login_required
@module_permission_required('branches', 'VIEW')
def branch_list(request):
    """View to list all branches."""
    search_query = request.GET.get('q', '').strip()
    status = 'inactive' if request.GET.get('status') == 'inactive' else 'active'
    active_branches = Branch.objects.filter(is_active=True)
    inactive_branches = Branch.objects.filter(is_active=False)
    branches = inactive_branches if status == 'inactive' else active_branches

    if search_query:
        branches = branches.filter(name__icontains=search_query)

    return render(request, 'branches/branch_list.html', {
        'branches': branches,
        'q': search_query,
        'status': status,
        'active_count': active_branches.count(),
        'inactive_count': inactive_branches.count(),
        'filters': [],
        'active_filters': [],
        'show_clear': bool(search_query),
    })


@login_required
@module_permission_required('branches', 'CREATE')
def branch_create(request):
    """View to create a new branch."""
    if request.method == 'POST':
        form = BranchForm(request.POST)
        if form.is_valid():
            branch = form.save()
            messages.success(request, f"Branch '{branch.name}' was created successfully.")
            return redirect('branches:list')
    else:
        form = BranchForm()

    return render(request, 'branches/branch_form.html', {
        'form': form,
        'action': 'Add',
    })


@login_required
@module_permission_required('branches', 'EDIT')
def branch_update(request, pk):
    """View to update an existing branch."""
    branch = get_object_or_404(Branch, pk=pk)
    
    if request.method == 'POST':
        form = BranchForm(request.POST, instance=branch)
        if form.is_valid():
            branch = form.save()
            messages.success(request, f"Branch '{branch.name}' was updated successfully.")
            return redirect('branches:list')
    else:
        form = BranchForm(instance=branch)

    return render(request, 'branches/branch_form.html', {
        'form': form,
        'action': 'Edit',
        'branch': branch,
    })


@login_required
@module_permission_required('branches', 'EDIT')
@require_POST
def branch_toggle_status(request, pk):
    """Activate or deactivate a branch from the branch list."""
    branch = get_object_or_404(Branch, pk=pk)

    if branch.is_active:
        if (
            request.POST.get('confirm_deactivation') != 'on'
            or request.POST.get('confirm_deactivation_final') != 'on'
        ):
            messages.warning(request, 'Complete both confirmations to make this branch inactive.')
            return redirect(f"{reverse('branches:list')}?status=active")

        with transaction.atomic():
            replacement_branch = Branch.objects.filter(is_active=True).exclude(pk=branch.pk).order_by('name').first()
            if replacement_branch:
                VetSchedule.objects.filter(branch=branch).update(branch=replacement_branch)
                RecurringSchedule.objects.filter(branch=branch).update(branch=replacement_branch)
            branch.is_active = False
            branch.save(update_fields=['is_active', 'updated_at'])
            get_user_model().objects.filter(branch=branch).update(branch=None)
            StaffMember.objects.filter(branch=branch).update(branch=None)
        success_message = f"Branch '{branch.name}' is now inactive."
    else:
        branch.is_active = True
        success_message = f"Branch '{branch.name}' is now active."

    if branch.is_active:
        branch.save(update_fields=['is_active', 'updated_at'])
    messages.success(request, success_message)
    status = 'active' if branch.is_active else 'inactive'
    return redirect(f"{reverse('branches:list')}?status={status}")
