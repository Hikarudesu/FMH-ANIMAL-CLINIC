from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required

from accounts.decorators import module_permission_required
from .models import Branch
from .forms import BranchForm


@login_required
@module_permission_required('branches', 'VIEW')
def branch_list(request):
    """View to list all branches."""
    search_query = request.GET.get('q', '')
    branches = Branch.objects.all()

    if search_query:
        branches = branches.filter(name__icontains=search_query)

    return render(request, 'branches/branch_list.html', {
        'branches': branches,
        'q': search_query,
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
@module_permission_required('branches', 'DELETE')
def branch_delete(request, pk):
    """View to handle branch deletion logic with confirmation."""
    branch = get_object_or_404(Branch, pk=pk)
    
    if request.method == 'POST':
        # Protect deletion if there are dependents (optional but good practice)
        # Assuming staff members might be assigned, checking before delete or catching exception:
        try:
            branch_name = branch.name
            branch.delete()
            messages.success(request, f"Branch '{branch_name}' was deleted.")
            return redirect('branches:list')
        except Exception as e:
            messages.error(request, f"Cannot delete branch: {e}")
            return redirect('branches:list')

    return render(request, 'branches/branch_confirm_delete.html', {
        'branch': branch
    })
