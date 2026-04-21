"""Views for Role-Based Access Control (RBAC) management.

Admin-only role management views. All views require:
- User must be logged in
- User must be admin (hierarchy >= 10) OR superuser
- User must have appropriate 'roles' or 'staff' module permissions
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from django.db import models, transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .decorators import module_permission_required, admin_only
from .models import User
from .rbac_models import Module, ModulePermission, Role, SpecialPermission, SUPERUSER_ONLY_MODULES, HIDDEN_FROM_MODULE_PERMISSIONS
from branches.models import Branch


def _assign_staff_default_modules(role):
    """Ensure baseline staff modules are always present for new staff roles."""
    default_codes = ['notifications']
    if role.code in {'superadmin', 'branch_admin', 'veterinarian', 'receptionist', 'vet_assistant'}:
        default_codes.append('soa')
    modules = Module.objects.filter(code__in=default_codes, is_active=True)
    for module in modules:
        ModulePermission.objects.get_or_create(
            role=role,
            module=module,
            permission_type=ModulePermission.PermissionType.VIEW,
            defaults={'restrict_to_branch': role.code != 'superadmin'},
        )


@login_required
@admin_only
@module_permission_required('roles', 'VIEW')
def role_list(request):
    """List all roles with their permissions summary.
    
    Note: Superadmin and User roles are hidden from this list.
    Superadmin is managed via is_superuser flag.
    User (Pet Owner) is implicit — users without assigned_role are pet owners.
    """
    from django.db.models import Count, Q

    search_query = request.GET.get('q', '').strip()

    # Get all staff roles except system roles (superadmin and user)
    # Note: 'superadmin' is hidden again as requested
    roles = Role.objects.prefetch_related(
        'module_permissions__module',
        'special_permissions__permission'
    ).exclude(
        code__in=['superadmin', 'user']  # Hide superadmin and user roles
    ).annotate(
        user_count=Count('users')
    ).order_by('-hierarchy_level', 'name')

    if search_query:
        roles = roles.filter(
            Q(name__icontains=search_query) |
            Q(code__icontains=search_query)
        )

    context = {
        'roles': roles,
        'search_value': search_query,
        'show_clear': bool(search_query),
        'active_tab': 'roles',
    }
    return render(request, 'accounts/roles/role_list.html', context)


@login_required
@admin_only
@module_permission_required('roles', 'CREATE')
def role_create(request):
    """Create a new role.
    
    Note: All roles created by administrators are automatically system roles.
    Superadmin role cannot be created here — relies solely on is_superuser flag.
    Superuser-only modules are hidden from the module selection.
    """
    # Filter out superuser-only modules from all users (these are reserved and should not be assignable to any role)
    # Also filter out modules that are hidden from the permissions UI (handled by special permissions)
    modules = Module.objects.filter(is_active=True).order_by('display_order')
    modules = modules.exclude(code__in=SUPERUSER_ONLY_MODULES)
    modules = modules.exclude(code__in=HIDDEN_FROM_MODULE_PERMISSIONS)

    # Only show non-deprecated permission types (APPROVE/EXPORT removed)
    permission_types = ModulePermission.PermissionType.choices
    special_permissions = SpecialPermission.objects.all()

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        # Auto-generate code from name
        import re
        code = re.sub(r'[^a-z0-9]+', '_', name.lower()).strip('_')
        description = request.POST.get('description', '').strip()
        hierarchy_level = int(request.POST.get('hierarchy_level', 0))
        # Roles created from Roles & Permissions are always staff roles
        is_staff_role = True
        # Automatically set as system role — no toggle needed
        is_system_role = True

        # Validate
        errors = []
        if not name:
            errors.append('Role name is required.')
        if code == 'superadmin':
            errors.append('Cannot create a role with code "superadmin". Use is_superuser flag instead.')
        if code == 'user':
            errors.append('Cannot create a role with code "user". Pet Owners are implicit.')
        if Role.objects.filter(code=code).exists():
            errors.append(f'A role with a similar name already exists.')
        if Role.objects.filter(name=name).exists():
            errors.append(f'Role name "{name}" already exists.')

        # Dashboard mutual exclusivity validation
        has_staff_dash = bool(request.POST.get('special_can_access_staff_dashboard'))
        has_admin_dash = bool(request.POST.get('special_can_access_admin_dashboard'))
        if has_staff_dash and has_admin_dash:
            errors.append(
                'A role cannot have both Staff Dashboard and Admin Dashboard access. '
                'Please select only one.'
            )

        if errors:
            for error in errors:
                messages.error(request, error)
            return render(request, 'accounts/roles/role_form.html', {
                'modules': modules,
                'permission_types': permission_types,
                'special_permissions': special_permissions,
                'form_data': request.POST,
            })

        with transaction.atomic():
            role = Role.objects.create(
                name=name,
                code=code,
                description=description,
                hierarchy_level=hierarchy_level,
                is_staff_role=is_staff_role,
                is_system_role=is_system_role,
            )

            # Add module permissions with per-module branch restriction
            for module in modules:
                branch_restrict = request.POST.get(f'branch_restrict_{module.code}') == 'on'
                for perm_type, _ in permission_types:
                    if request.POST.get(f'perm_{module.code}_{perm_type}'):
                        ModulePermission.objects.create(
                            role=role,
                            module=module,
                            permission_type=perm_type,
                            restrict_to_branch=branch_restrict,
                        )

            # Add special permissions
            for sp in special_permissions:
                if request.POST.get(f'special_{sp.code}'):
                    role.special_permissions.create(permission=sp)

            _assign_staff_default_modules(role)

        messages.success(request, f'Role "{name}" created successfully.')
        return redirect('accounts:role_list')

    context = {
        'modules': modules,
        'permission_types': permission_types,
        'special_permissions': special_permissions,
        'form_data': {},
        'active_tab': 'roles',
    }
    return render(request, 'accounts/roles/role_form.html', context)


@login_required
@admin_only
@module_permission_required('roles', 'EDIT')
def role_edit(request, role_id):
    """Edit an existing role.
    
    Note: Superadmin role cannot be edited — it relies solely on is_superuser flag.
    Superuser-only modules are hidden from the module selection.
    """
    role = get_object_or_404(Role, pk=role_id)

    # Prevent editing superadmin role
    if role.code == 'superadmin':
        messages.warning(request, 'Superadmin role cannot be edited. Use is_superuser flag instead.')
        return redirect('accounts:role_list')

    # Prevent editing user role
    if role.code == 'user':
        messages.warning(request, 'User role cannot be edited. Pet Owners are implicit.')
        return redirect('accounts:role_list')

    # Prevent editing system roles (unless superuser)
    if role.is_system_role and not request.user.is_superuser:
        messages.warning(request, 'System roles cannot be edited. Contact administrator.')
        return redirect('accounts:role_list')

    # Filter out superuser-only modules from all users (these are reserved and should not be assignable to any role)
    # Also filter out modules that are hidden from the permissions UI (handled by special permissions)
    modules = Module.objects.filter(is_active=True).order_by('display_order')
    modules = modules.exclude(code__in=SUPERUSER_ONLY_MODULES)
    modules = modules.exclude(code__in=HIDDEN_FROM_MODULE_PERMISSIONS)

    permission_types = ModulePermission.PermissionType.choices
    special_permissions = SpecialPermission.objects.all()

    # Get current permissions
    current_perms = set(
        role.module_permissions.values_list('module__code', 'permission_type')
    )
    current_special = set(
        role.special_permissions.values_list('permission__code', flat=True)
    )

    # Get current per-module branch restrictions
    current_branch_restrict = set(
        role.module_permissions.filter(restrict_to_branch=True)
        .values_list('module__code', flat=True).distinct()
    )

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        description = request.POST.get('description', '').strip()
        hierarchy_level = int(request.POST.get('hierarchy_level', 0))
        # Roles edited in Roles & Permissions remain staff roles
        is_staff_role = True
        # Keep is_system_role as-is — no toggle, stays True
        is_system_role = role.is_system_role

        # Validate
        errors = []
        if not name:
            errors.append('Role name is required.')
        if Role.objects.filter(name=name).exclude(pk=role_id).exists():
            errors.append(f'Role name "{name}" already exists.')

        # Dashboard mutual exclusivity validation
        has_staff_dash = bool(request.POST.get('special_can_access_staff_dashboard'))
        has_admin_dash = bool(request.POST.get('special_can_access_admin_dashboard'))
        if has_staff_dash and has_admin_dash:
            errors.append(
                'A role cannot have both Staff Dashboard and Admin Dashboard access. '
                'Please select only one.'
            )

        if errors:
            for error in errors:
                messages.error(request, error)
            return render(request, 'accounts/roles/role_form.html', {
                'role': role,
                'modules': modules,
                'permission_types': permission_types,
                'special_permissions': special_permissions,
                'current_perms': current_perms,
                'current_special': current_special,
                'current_branch_restrict': current_branch_restrict,
                'form_data': request.POST,
            })

        with transaction.atomic():
            role.name = name
            role.description = description
            role.hierarchy_level = hierarchy_level
            role.is_staff_role = is_staff_role
            role.is_system_role = is_system_role
            role.save()

            # Update module permissions
            role.module_permissions.all().delete()
            for module in modules:
                branch_restrict = request.POST.get(f'branch_restrict_{module.code}') == 'on'
                for perm_type, _ in permission_types:
                    if request.POST.get(f'perm_{module.code}_{perm_type}'):
                        ModulePermission.objects.create(
                            role=role,
                            module=module,
                            permission_type=perm_type,
                            restrict_to_branch=branch_restrict,
                        )

            # Update special permissions
            role.special_permissions.all().delete()
            for sp in special_permissions:
                if request.POST.get(f'special_{sp.code}'):
                    role.special_permissions.create(permission=sp)

            _assign_staff_default_modules(role)

        messages.success(request, f'Role "{name}" updated successfully.')
        return redirect('accounts:role_list')

    context = {
        'role': role,
        'modules': modules,
        'permission_types': permission_types,
        'special_permissions': special_permissions,
        'current_perms': current_perms,
        'current_special': current_special,
        'current_branch_restrict': current_branch_restrict,
        'form_data': {},
        'active_tab': 'roles',
    }
    return render(request, 'accounts/roles/role_form.html', context)


@login_required
@admin_only
@module_permission_required('roles', 'DELETE')
@require_POST
def role_delete(request, role_id):
    """Delete a role."""
    role = get_object_or_404(Role, pk=role_id)

    # Prevent deleting system roles (unless superuser)
    if role.is_system_role and not request.user.is_superuser:
        messages.error(request, 'System roles cannot be deleted. Contact administrator.')
        return redirect('accounts:role_list')

    # Check if role is in use
    user_count = role.users.count()

    # Non-superusers cannot delete roles with assigned users
    if user_count > 0 and not request.user.is_superuser:
        messages.error(
            request,
            f'Cannot delete role "{role.name}". It is assigned to {user_count} user(s).'
        )
        return redirect('accounts:role_list')

    name = role.name

    # If deleting a role with users, unassign them first
    if user_count > 0:
        role.users.all().update(assigned_role=None)
        messages.warning(
            request,
            f'{user_count} user(s) were unassigned from this role.'
        )

    role.delete()
    messages.success(request, f'Role "{name}" deleted successfully.')
    return redirect('accounts:role_list')


@login_required
@admin_only
@module_permission_required('roles', 'VIEW')
def role_detail(request, role_id):
    """View role details and assigned users."""
    role = get_object_or_404(
        Role.objects.prefetch_related(
            'module_permissions__module',
            'special_permissions__permission',
            'users'
        ),
        pk=role_id
    )

    # Group permissions by module
    module_perms = {}
    for mp in role.module_permissions.all():
        if mp.module.code not in module_perms:
            module_perms[mp.module.code] = {
                'module': mp.module,
                'permissions': [],
                'restrict_to_branch': mp.restrict_to_branch,
            }
        module_perms[mp.module.code]['permissions'].append(mp.permission_type)
        # If any permission for this module has branch restriction, mark it
        if mp.restrict_to_branch:
            module_perms[mp.module.code]['restrict_to_branch'] = True

    context = {
        'role': role,
        'module_perms': module_perms,
        'assigned_users': role.users.select_related('branch')[:50],
        'active_tab': 'roles',
    }
    return render(request, 'accounts/roles/role_detail.html', context)


# ============================================================================
# User Role Assignment Views
# ============================================================================

@login_required
@admin_only
@module_permission_required('staff', 'EDIT')
def user_role_list(request):
    """List staff users with their role assignments.
    
    Pet Owners are "Shadow Users" — they are not shown in this management UI.
    Only staff members (users with is_staff_role=True or superusers) appear here.
    """
    search_query = request.GET.get('q', '').strip()
    role_filter = request.GET.get('role', '')
    branch_filter = request.GET.get('branch', '')

    # Base queryset — ONLY show staff users (not Pet Owners)
    users = User.objects.select_related('assigned_role', 'branch').filter(
        models.Q(assigned_role__is_staff_role=True) | models.Q(is_superuser=True)
    ).distinct()

    # Apply search filter
    if search_query:
        users = users.filter(
            models.Q(username__icontains=search_query) |
            models.Q(first_name__icontains=search_query) |
            models.Q(last_name__icontains=search_query) |
            models.Q(email__icontains=search_query)
        )

    # Apply role filter (only staff roles)
    if role_filter:
        try:
            users = users.filter(assigned_role_id=int(role_filter))
        except ValueError:
            pass

    # Apply branch filter
    if branch_filter:
        try:
            users = users.filter(branch_id=int(branch_filter))
        except ValueError:
            pass

    users = users.order_by('username')

    # Get only staff roles for the filter dropdown (exclude superadmin and user roles)
    # Note: 'superadmin' is hidden again as requested
    roles = Role.objects.filter(is_staff_role=True).exclude(code__in=['superadmin', 'user']).order_by('-hierarchy_level', 'name')
    
    # Get all branches for the filter dropdown
    branches = Branch.objects.filter(is_active=True).order_by('name')

    # Build filter list for filter_bar component
    role_filters = [
        {
            'name': 'role',
            'icon': 'bx-shield-quarter',
            'default_label': 'All Roles',
            'has_value': bool(role_filter),
            'selected_label': '',
            'options': []
        },
        {
            'name': 'branch',
            'icon': 'bx-building-house',
            'default_label': 'All Branches',
            'has_value': bool(branch_filter),
            'selected_label': '',
            'options': []
        }
    ]

    role_opts = []
    # Populate role filter options
    for role in roles:
        is_selected = str(role.id) == role_filter
        role_opts.append({
            'value': role.id,
            'label': role.name,
            'selected': is_selected
        })
        if is_selected:
            role_filters[0]['selected_label'] = role.name
    role_filters[0]['options'] = role_opts

    branch_opts = []
    # Populate branch filter options
    for branch in branches:
        is_selected = str(branch.id) == branch_filter
        branch_opts.append({
            'value': branch.id,
            'label': branch.name,
            'selected': is_selected
        })
        if is_selected:
            role_filters[1]['selected_label'] = branch.name
    role_filters[1]['options'] = branch_opts

    # Show clear button if any filter is active
    show_clear = bool(search_query or role_filter or branch_filter)

    context = {
        'users': users,
        'roles': roles,
        'active_tab': 'staff',
        'search_value': search_query,
        'role_filters': role_filters,
        'show_clear': show_clear,
    }
    return render(request, 'accounts/roles/user_role_list.html', context)


@login_required
@admin_only
@module_permission_required('staff', 'EDIT')
@require_POST
def assign_user_role(request, user_id):
    """Assign a role to a staff user.
    
    Only staff users can be modified here. Pet Owners cannot be promoted.
    """
    from employees.models import StaffMember

    user = get_object_or_404(User, pk=user_id)
    role_id = request.POST.get('role_id')

    old_role = user.assigned_role

    if role_id:
        role = get_object_or_404(Role, pk=role_id)
        user.assigned_role = role
        user.save()

        # Auto-create or update StaffMember if staff role
        if role.is_staff_role:
            # Map role codes to StaffMember positions
            role_to_position = {
                'veterinarian': StaffMember.Position.VETERINARIAN,
                'vet_assistant': StaffMember.Position.VET_ASSISTANT,
                'receptionist': StaffMember.Position.RECEPTIONIST,
                'branch_admin': StaffMember.Position.ADMIN,
                'superadmin': StaffMember.Position.ADMIN,
                'admin': StaffMember.Position.ADMIN,
            }
            position = role_to_position.get(role.code, StaffMember.Position.RECEPTIONIST)

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

        messages.success(request, f'Role "{role.name}" assigned to {user.username}.')
    else:
        user.assigned_role = None
        user.save()

        # Deactivate StaffMember if removing staff role
        if old_role and old_role.is_staff_role:
            try:
                staff_profile = user.staff_profile
                staff_profile.is_active = False
                staff_profile.save()
            except ObjectDoesNotExist:
                pass  # No staff profile exists

        messages.success(request, f'Role removed from {user.username}.')

    # Return JSON for AJAX requests
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'success': True,
            'message': f'Role updated for {user.username}',
            'role_name': role.name if role_id else user.get_display_role()
        })

    return redirect('accounts:user_role_list')


# ============================================================================
# API Endpoints
# ============================================================================

@login_required
@admin_only
@module_permission_required('roles', 'VIEW')
def get_role_permissions(request, role_id):
    """API endpoint to get role permissions (for AJAX)."""
    role = get_object_or_404(Role, pk=role_id)

    permissions: dict = {}
    branch_restrictions: dict = {}
    for mp in role.module_permissions.select_related('module').all():
        if mp.module.code not in permissions:
            permissions[mp.module.code] = []
        permissions[mp.module.code].append(mp.permission_type)
        if mp.restrict_to_branch:
            branch_restrictions.update({mp.module.code: True})

    special = list(
        role.special_permissions.values_list('permission__code', flat=True)
    )

    return JsonResponse({
        'permissions': permissions,
        'special_permissions': special,
        'branch_restrictions': branch_restrictions,
        'hierarchy_level': role.hierarchy_level,
        'is_staff_role': role.is_staff_role,
    })


@login_required
@admin_only
@module_permission_required('roles', 'VIEW')
def module_list_api(request):
    """API endpoint to get all modules."""
    modules = Module.objects.filter(is_active=True).order_by('display_order')

    # Filter out superuser-only modules from all users (these are reserved and should not be assignable to any role)
    modules = modules.exclude(code__in=SUPERUSER_ONLY_MODULES)

    data = []
    for module in modules:
        data.append({
            'code': module.code,
            'name': module.name,
            'icon': module.icon,
            'description': module.description,
        })

    return JsonResponse({'modules': data})


@login_required
@admin_only
def get_hierarchy_presets(request):
    """API endpoint to get permission presets for a hierarchy level or role code.

    Dynamically fetches the current permissions from an existing role in the DB
    rather than using static hardcoded presets.  Accepts either:
      - ?level=<int>          — find the first role at that hierarchy level
      - ?role_code=<string>   — find the role by its code (for Quick Preset buttons)
      - &exclude_role=<int>   — optional role ID to exclude (the role being edited)
    """
    level = request.GET.get('level')
    role_code = request.GET.get('role_code', '').strip()
    exclude_id = request.GET.get('exclude_role')

    qs = Role.objects.all()

    # Exclude the role currently being edited so it doesn't reference itself
    if exclude_id:
        try:
            qs = qs.exclude(pk=int(exclude_id))
        except (ValueError, TypeError):
            pass

    # Determine which role to use as the preset source
    reference_role = None
    if role_code:
        reference_role = qs.filter(code=role_code).first()
    elif level is not None:
        try:
            reference_role = qs.filter(hierarchy_level=int(level)).first()
        except (ValueError, TypeError):
            pass

    if not reference_role:
        return JsonResponse({'found': False})

    # Build the permissions dict (same structure as get_role_permissions)
    permissions = {}
    branch_restrictions = {}
    for mp in reference_role.module_permissions.select_related('module').all():
        if mp.module.code not in permissions:
            permissions[mp.module.code] = []
        permissions[mp.module.code].append(mp.permission_type)
        if mp.restrict_to_branch:
            branch_restrictions[mp.module.code] = True

    special = list(
        reference_role.special_permissions.values_list('permission__code', flat=True)
    )

    return JsonResponse({
        'found': True,
        'permissions': permissions,
        'special_permissions': special,
        'branch_restrictions': branch_restrictions,
        'hierarchy_level': reference_role.hierarchy_level,
        'role_name': reference_role.name,
    })
