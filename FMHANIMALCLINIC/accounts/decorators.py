"""
Decorators and mixins for Role-Based Access Control (RBAC).

Provides:
- hierarchy_required: Requires user to have at least a specific hierarchy level
- module_permission_required: Requires module access with optional permission level
- special_permission_required: Requires a specific special permission
- branch_required: Requires user to be assigned to a branch
- admin_only: Shortcut for hierarchy level >= 10 (Superadmin)
- staff_only: Shortcut for any clinic staff role
- BranchFilterMixin: Automatically filters querysets by user's branch
- ModulePermissionMixin: Checks module permissions for class-based views
"""
from functools import wraps

from django.contrib import messages
from django.shortcuts import redirect


def hierarchy_required(min_level):
    """
    Decorator that requires user to have at least the specified hierarchy level.

    Usage:
        @login_required
        @hierarchy_required(8)  # Branch Admin or higher
        def branch_admin_view(request):
            ...

        @login_required
        @hierarchy_required(6)  # Veterinarian or higher
        def vet_view(request):
            ...
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login_page')

            # Superusers always pass
            if request.user.is_superuser:
                return view_func(request, *args, **kwargs)

            # Check hierarchy level
            if request.user.assigned_role and request.user.assigned_role.hierarchy_level >= min_level:
                return view_func(request, *args, **kwargs)

            messages.warning(request, 'You do not have sufficient permissions.')
            if request.user.is_clinic_staff():
                return redirect('admin_dashboard')
            return redirect('user_dashboard')
        return wrapper
    return decorator


def module_permission_required(module_code, permission_type=None, redirect_url=None):
    """
    Decorator that checks if user has permission for a specific module.

    Args:
        module_code: The Module code (e.g., 'appointments', 'patients')
        permission_type: Optional specific permission ('VIEW', 'CREATE', 'EDIT', 'DELETE')
                        If None, checks for any access to the module
        redirect_url: Custom redirect URL on permission failure (optional)

    Usage:
        @login_required
        @module_permission_required('appointments', 'CREATE')
        def create_appointment(request):
            ...

        @login_required
        @module_permission_required('inventory')  # Any access
        def view_inventory(request):
            ...
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login_page')

            # Check module permission
            if request.user.has_module_permission(module_code, permission_type):
                return view_func(request, *args, **kwargs)

            # Permission denied
            messages.warning(
                request,
                f'You do not have {permission_type or "access"} permission for this section.'
            )

            if redirect_url:
                return redirect(redirect_url)

            if request.user.is_clinic_staff():
                return redirect('admin_dashboard')
            return redirect('user_dashboard')
        return wrapper
    return decorator


def special_permission_required(permission_code, redirect_url=None):
    """
    Decorator that checks if user has a special permission.

    Args:
        permission_code: The SpecialPermission code
        redirect_url: Custom redirect URL on permission failure (optional)

    Usage:
        @login_required
        @special_permission_required('can_view_own_payslips')
        def my_payslips(request):
            ...
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login_page')

            if request.user.has_special_permission(permission_code):
                return view_func(request, *args, **kwargs)

            messages.warning(request, 'You do not have permission to access this feature.')

            if redirect_url:
                return redirect(redirect_url)

            if request.user.is_clinic_staff():
                return redirect('admin_dashboard')
            return redirect('user_dashboard')
        return wrapper
    return decorator


def branch_required(redirect_url=None):
    """
    Decorator that requires the user to be assigned to a branch.

    Usage:
        @login_required
        @branch_required()
        def branch_specific_view(request):
            ...
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login_page')

            if request.user.branch:
                return view_func(request, *args, **kwargs)

            messages.warning(
                request,
                'You must be assigned to a branch to access this feature.'
            )

            if redirect_url:
                return redirect(redirect_url)

            if request.user.is_clinic_staff():
                return redirect('admin_dashboard')
            return redirect('user_dashboard')
        return wrapper
    return decorator


def admin_only(view_func):
    """
    Shortcut decorator for admin-only views (hierarchy level >= 10).

    Usage:
        @login_required
        @admin_only
        def admin_settings(request):
            ...
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login_page')

        # Superusers always pass
        if request.user.is_superuser:
            return view_func(request, *args, **kwargs)

        # Check RBAC role hierarchy
        if request.user.assigned_role and request.user.assigned_role.hierarchy_level >= 10:
            return view_func(request, *args, **kwargs)

        messages.warning(request, 'This action requires administrator privileges.')

        if request.user.is_clinic_staff():
            return redirect('admin_dashboard')
        return redirect('user_dashboard')
    return wrapper


def staff_only(view_func):
    """
    Shortcut decorator for staff-only views (any clinic staff).

    Usage:
        @login_required
        @staff_only
        def staff_dashboard(request):
            ...
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login_page')

        if request.user.is_clinic_staff():
            return view_func(request, *args, **kwargs)

        messages.warning(request, 'This area is for clinic staff only.')
        return redirect('user_dashboard')
    return wrapper


# ============================================================================
# Class-Based View Mixins
# ============================================================================

class BranchFilterMixin:
    """
    Mixin that automatically filters querysets by the user's branch.

    For users whose role restricts them to their branch, this mixin filters
    the queryset to only show records associated with their branch.

    Requires the model to have a 'branch' field.

    Usage:
        class PatientListView(BranchFilterMixin, ListView):
            model = Patient
            branch_field = 'branch'  # Optional, defaults to 'branch'
            module_code = 'patients'  # For per-module branch restriction

        class RecordListView(BranchFilterMixin, ListView):
            model = MedicalRecord
            branch_field = 'patient__branch'  # For related field filtering
            module_code = 'medical_records'
    """
    branch_field = 'branch'  # Override this for related field lookups
    module_code = None  # Override for per-module branch restriction

    def get_queryset(self):
        """Filter queryset by user's branch if they are branch-restricted."""
        queryset = super().get_queryset()

        user = self.request.user

        # Skip filtering for superusers
        if user.is_superuser:
            return queryset

        # Check per-module branch restriction
        if self.module_code:
            if not user.is_module_branch_restricted(self.module_code):
                return queryset
        else:
            if not user.is_branch_restricted():
                return queryset

        # Filter by branch
        if user.branch:
            filter_kwargs = {self.branch_field: user.branch}
            return queryset.filter(**filter_kwargs)

        # No branch assigned - return empty queryset for safety
        return queryset.none()


class ModulePermissionMixin:
    """
    Mixin that checks module permissions for class-based views.

    Usage:
        class PatientCreateView(ModulePermissionMixin, CreateView):
            model = Patient
            module_code = 'patients'
            permission_type = 'CREATE'

        class PatientListView(ModulePermissionMixin, ListView):
            model = Patient
            module_code = 'patients'
            permission_type = 'VIEW'  # Optional, defaults to VIEW
    """
    module_code = None  # Required: Module code
    permission_type = 'VIEW'  # Default permission type
    permission_denied_message = 'You do not have permission to access this resource.'

    def dispatch(self, request, *args, **kwargs):
        """Check permissions before dispatching."""
        if not request.user.is_authenticated:
            return redirect('login_page')

        if self.module_code is None:
            raise ValueError("module_code must be set on the view")

        if not request.user.has_module_permission(self.module_code, self.permission_type):
            messages.warning(request, self.permission_denied_message)
            return self.handle_no_permission()

        return super().dispatch(request, *args, **kwargs)

    def handle_no_permission(self):
        """Handle permission denied."""
        if self.request.user.is_clinic_staff():
            return redirect('admin_dashboard')
        return redirect('user_dashboard')


class OwnRecordMixin:
    """
    Mixin for views where users can only access their own records.

    Useful for features like "view own payslips", "edit own schedule".

    Usage:
        class MyPayslipsView(OwnRecordMixin, ListView):
            model = Payslip
            user_field = 'employee__user'  # Field path to the user

        class MyScheduleView(OwnRecordMixin, ListView):
            model = VetSchedule
            user_field = 'staff__user'
    """
    user_field = 'user'  # Override for related field lookups
    allow_admin_override = True  # Admins can see all records

    def get_queryset(self):
        """Filter to only the user's own records."""
        queryset = super().get_queryset()

        user = self.request.user

        # Allow admin override if configured
        if self.allow_admin_override:
            if user.is_superuser:
                return queryset
            if user.assigned_role and user.assigned_role.hierarchy_level >= 10:
                return queryset

        # Filter to user's own records
        filter_kwargs = {self.user_field: user}
        return queryset.filter(**filter_kwargs)


class CombinedPermissionMixin(ModulePermissionMixin, BranchFilterMixin):
    """
    Combines module permission checking with branch filtering.

    Usage:
        class PatientListView(CombinedPermissionMixin, ListView):
            model = Patient
            module_code = 'patients'
            permission_type = 'VIEW'
            branch_field = 'branch'
    """


# ============================================================================
# Helper Functions
# ============================================================================

def filter_queryset_by_branch(queryset, user, branch_field='branch', module_code=None):
    """
    Utility function to filter a queryset by user's branch.

    Args:
        queryset: Django QuerySet to filter
        user: User instance
        branch_field: Field name or lookup path for the branch
        module_code: Optional module code for per-module branch restriction

    Returns:
        Filtered QuerySet
    """
    # Superusers see all
    if user.is_superuser:
        return queryset

    # Check per-module or global branch restriction
    if module_code:
        if not user.is_module_branch_restricted(module_code):
            return queryset
    else:
        if not user.is_branch_restricted():
            return queryset

    # Filter by branch
    if user.branch:
        filter_kwargs = {branch_field: user.branch}
        return queryset.filter(**filter_kwargs)

    # No branch assigned - return empty for safety
    return queryset.none()


def get_user_branches(user, module_code=None):
    """
    Get all branches a user can access.

    Args:
        user: User instance
        module_code: Optional module code for per-module branch restriction

    Returns:
        QuerySet of Branch objects
    """
    from branches.models import Branch

    # Superusers see all branches
    if user.is_superuser:
        return Branch.objects.filter(is_active=True)

    # Check per-module or global restriction
    if module_code:
        if not user.is_module_branch_restricted(module_code):
            return Branch.objects.filter(is_active=True)
    else:
        if not user.is_branch_restricted():
            return Branch.objects.filter(is_active=True)

    # Branch-restricted users see only their branch
    if user.branch:
        return Branch.objects.filter(pk=user.branch.pk)

    return Branch.objects.none()


def check_object_branch_access(user, obj, branch_field='branch', module_code=None):
    """
    Check if a user has access to a specific object based on branch.

    Args:
        user: User instance
        obj: Model instance to check
        branch_field: Field name or path to get the branch
        module_code: Optional module code for per-module branch restriction

    Returns:
        bool: True if user has access
    """
    if user.is_superuser:
        return True

    if module_code:
        if not user.is_module_branch_restricted(module_code):
            return True
    else:
        if not user.is_branch_restricted():
            return True

    # Get the object's branch
    obj_branch = obj
    for field in branch_field.split('__'):
        obj_branch = getattr(obj_branch, field, None)
        if obj_branch is None:
            return True  # No branch assigned to object, allow access

    # Compare with user's branch
    return user.branch == obj_branch
