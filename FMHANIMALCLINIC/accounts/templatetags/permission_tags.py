"""
Template tags for RBAC permission checking.

Usage:
    {% load permission_tags %}

    {# Check if user has access to a module #}
    {% if user|has_module:'appointments' %}
        <a href="{% url 'appointments:admin_list' %}">Appointments</a>
    {% endif %}

    {# Check specific permission level #}
    {% if user|has_module_permission:'appointments:CREATE' %}
        <button>Create Appointment</button>
    {% endif %}

    {# Check special permissions #}
    {% if user|has_special_permission:'can_view_own_payslips' %}
        <a href="{% url 'payroll:my_payslips' %}">My Payslips</a>
    {% endif %}

    {# Get user's role name #}
    {{ user|role_name }}

    {# Check if user is admin #}
    {% if user|is_admin %}
        <a href="{% url 'settings:admin_settings' %}">Settings</a>
    {% endif %}
"""
from django import template

register = template.Library()


@register.filter(name='has_module')
def has_module(user, module_code):
    """
    Check if user has access to a module (any permission level).

    Usage:
        {% if user|has_module:'appointments' %}
            ...
        {% endif %}
    """
    if not user or not user.is_authenticated:
        return False
    return user.has_module_permission(module_code)


@register.filter(name='has_module_permission')
def has_module_permission(user, module_permission):
    """
    Check if user has a specific permission for a module.

    Args:
        module_permission: String in format 'module_code:PERMISSION_TYPE'
                          e.g., 'appointments:CREATE', 'inventory:DELETE'

    Usage:
        {% if user|has_module_permission:'appointments:CREATE' %}
            <button>Create Appointment</button>
        {% endif %}
    """
    if not user or not user.is_authenticated:
        return False

    try:
        module_code, permission_type = module_permission.split(':')
        return user.has_module_permission(module_code, permission_type)
    except ValueError:
        # If no permission type specified, check for any access
        return user.has_module_permission(module_permission)


@register.filter(name='has_special_permission')
def has_special_permission(user, permission_code):
    """
    Check if user has a special permission.

    Usage:
        {% if user|has_special_permission:'can_view_own_payslips' %}
            ...
        {% endif %}
    """
    if not user or not user.is_authenticated:
        return False
    return user.has_special_permission(permission_code)


@register.filter(name='has_nav_module')
def has_nav_module(user, module_code):
    """Navigation-only module visibility check."""
    if not user or not user.is_authenticated:
        return False
    return user.has_navigation_module_access(module_code)


@register.filter(name='has_nav_special_permission')
def has_nav_special_permission(user, permission_code):
    """Navigation-only special permission visibility check."""
    if not user or not user.is_authenticated:
        return False
    return user.has_navigation_special_permission(permission_code)


@register.filter(name='role_name')
def role_name(user):
    """
    Get the display name for the user's role.

    Usage:
        <span class="role-badge">{{ user|role_name }}</span>
    """
    if not user or not user.is_authenticated:
        return ''
    return user.get_display_role()


@register.filter(name='is_admin')
def is_admin(user):
    """
    Check if user is an admin (hierarchy level >= 10 or ADMIN role).

    Usage:
        {% if user|is_admin %}
            ...
        {% endif %}
    """
    if not user or not user.is_authenticated:
        return False

    if user.is_superuser:
        return True

    if user.assigned_role and user.assigned_role.hierarchy_level >= 10:
        return True

    return False


@register.filter(name='is_branch_admin')
def is_branch_admin(user):
    """
    Check if user is at least a branch admin (hierarchy level >= 8).

    Usage:
        {% if user|is_branch_admin %}
            ...
        {% endif %}
    """
    if not user or not user.is_authenticated:
        return False

    if user.is_superuser:
        return True

    if user.assigned_role and user.assigned_role.hierarchy_level >= 8:
        return True

    return False


@register.filter(name='is_staff_role')
def is_staff_role(user):
    """
    Check if user has a staff role (can access admin portal).

    Usage:
        {% if user|is_staff_role %}
            ...
        {% endif %}
    """
    if not user or not user.is_authenticated:
        return False
    return user.is_clinic_staff()


@register.filter(name='is_branch_restricted')
def is_branch_restricted(user):
    """
    Check if user's data access is restricted to their branch (any module).

    Usage:
        {% if user|is_branch_restricted %}
            <span>Showing data for {{ user.branch.name }} only</span>
        {% endif %}
    """
    if not user or not user.is_authenticated:
        return True
    return user.is_branch_restricted()


@register.filter(name='is_module_branch_restricted')
def is_module_branch_restricted(user, module_code):
    """
    Check if user's data access is restricted to their branch for a specific module.

    Usage:
        {% if user|is_module_branch_restricted:'appointments' %}
            <span>Showing data for {{ user.branch.name }} only</span>
        {% endif %}
    """
    if not user or not user.is_authenticated:
        return True
    return user.is_module_branch_restricted(module_code)


@register.simple_tag(takes_context=True)
def can_access_module(context, module_code, permission_type=None):
    """
    Check module access with optional permission type.

    Usage:
        {% can_access_module 'appointments' as can_view_appointments %}
        {% if can_view_appointments %}
            ...
        {% endif %}

        {% can_access_module 'appointments' 'CREATE' as can_create %}
        {% if can_create %}
            <button>New Appointment</button>
        {% endif %}
    """
    user = context.get('user') or context.get('request', {}).user
    if not user or not user.is_authenticated:
        return False
    return user.has_module_permission(module_code, permission_type)


@register.simple_tag(takes_context=True)
def get_accessible_modules(context):
    """
    Get all modules the current user can access.

    Usage:
        {% get_accessible_modules as modules %}
        {% for module in modules %}
            <a href="...">{{ module.name }}</a>
        {% endfor %}
    """
    request = context.get('request')
    if not request or not request.user.is_authenticated:
        return []
    return request.user.get_accessible_modules()


# ============================================================================
# Hierarchy and Role Code Checks
# ============================================================================

@register.filter(name='has_hierarchy_level')
def has_hierarchy_level(user, min_level):
    """
    Check if user has at least the specified hierarchy level.

    Usage:
        {% if user|has_hierarchy_level:8 %}  {# Branch Admin or higher #}
            ...
        {% endif %}
        {% if user|has_hierarchy_level:6 %}  {# Veterinarian or higher #}
            ...
        {% endif %}
    """
    if not user or not user.is_authenticated:
        return False

    if user.is_superuser:
        return True

    try:
        min_level = int(min_level)
    except (ValueError, TypeError):
        return False

    if user.assigned_role:
        return user.assigned_role.hierarchy_level >= min_level

    return False


@register.filter(name='has_role_code')
def has_role_code(user, role_code):
    """
    Check if user has a specific role code.

    Usage:
        {% if user|has_role_code:'veterinarian' %}
            ...
        {% endif %}
    """
    if not user or not user.is_authenticated:
        return False

    if user.assigned_role:
        return user.assigned_role.code == role_code

    return False


# ============================================================================
# Context-aware permission checks
# ============================================================================

@register.simple_tag(takes_context=True)
def can_edit_schedule(context, schedule):
    """
    Check if user can edit a specific schedule entry.
    Vets can edit their own schedules, admins can edit any.

    Usage:
        {% can_edit_schedule schedule as can_edit %}
        {% if can_edit %}
            <button>Edit</button>
        {% endif %}
    """
    request = context.get('request')
    if not request or not request.user.is_authenticated:
        return False

    user = request.user

    # Admins can edit any schedule
    if user.is_superuser or user.has_module_permission('schedule', 'EDIT'):
        return True

    # Check if this is the user's own schedule
    if hasattr(schedule, 'staff') and hasattr(schedule.staff, 'user'):
        return schedule.staff.user == user

    return False


@register.simple_tag(takes_context=True)
def can_view_payslip(context, payslip):
    """
    Check if user can view a specific payslip.
    Users can view their own, admins can view all.

    Usage:
        {% can_view_payslip payslip as can_view %}
        {% if can_view %}
            <a href="...">View Payslip</a>
        {% endif %}
    """
    request = context.get('request')
    if not request or not request.user.is_authenticated:
        return False

    user = request.user

    # Admins can view all payslips
    if user.is_superuser or user.has_module_permission('payroll', 'VIEW'):
        return True

    # Check if this is the user's own payslip
    if hasattr(payslip, 'staff') and hasattr(payslip.staff, 'user'):
        if payslip.staff.user == user:
            return user.has_special_permission('can_view_own_payslips')

    return False


# ============================================================================
# Button Visibility Helpers for CRUD Operations
# ============================================================================

@register.simple_tag(takes_context=True)
def can_create(context, module_code):
    """
    Check if user can create items in a module.
    
    Usage:
        {% can_create 'appointments' as show_create_btn %}
        {% if show_create_btn %}
            <button>Create Appointment</button>
        {% endif %}
    """
    user = context.get('user') or getattr(context.get('request'), 'user', None)
    if not user or not user.is_authenticated:
        return False
    return user.has_module_permission(module_code, 'CREATE')


@register.simple_tag(takes_context=True)
def can_edit(context, module_code):
    """
    Check if user can edit items in a module.
    
    Usage:
        {% can_edit 'appointments' as show_edit_btn %}
        {% if show_edit_btn %}
            <button>Edit</button>
        {% endif %}
    """
    user = context.get('user') or getattr(context.get('request'), 'user', None)
    if not user or not user.is_authenticated:
        return False
    return user.has_module_permission(module_code, 'EDIT')


@register.simple_tag(takes_context=True)
def can_delete(context, module_code):
    """
    Check if user can delete items in a module.
    
    Usage:
        {% can_delete 'appointments' as show_delete_btn %}
        {% if show_delete_btn %}
            <button>Delete</button>
        {% endif %}
    """
    user = context.get('user') or getattr(context.get('request'), 'user', None)
    if not user or not user.is_authenticated:
        return False
    return user.has_module_permission(module_code, 'DELETE')


@register.simple_tag(takes_context=True)
def can_view(context, module_code):
    """
    Check if user can view items in a module.
    
    Usage:
        {% can_view 'appointments' as show_view_btn %}
        {% if show_view_btn %}
            <a href="...">View Details</a>
        {% endif %}
    """
    user = context.get('user') or getattr(context.get('request'), 'user', None)
    if not user or not user.is_authenticated:
        return False
    return user.has_module_permission(module_code, 'VIEW')


@register.simple_tag(takes_context=True)
def show_branch_dropdown(context, module_code):
    """
    Check if branch dropdown should be shown for a module.
    Returns False if user is branch-restricted for this module.
    
    Usage:
        {% show_branch_dropdown 'appointments' as show_branch_select %}
        {% if show_branch_select %}
            <select name="branch">...</select>
        {% endif %}
    """
    user = context.get('user') or getattr(context.get('request'), 'user', None)
    if not user or not user.is_authenticated:
        return False
    
    # Superusers always see branch dropdown
    if user.is_superuser:
        return True
    
    # Check if user is branch-restricted for this module
    if user.is_module_branch_restricted(module_code):
        return False
    
    return True


@register.simple_tag(takes_context=True)
def get_user_branch_name(context):
    """
    Get the name of the user's assigned branch.
    
    Usage:
        {% get_user_branch_name as branch_name %}
        <span>Showing data for: {{ branch_name }}</span>
    """
    user = context.get('user') or getattr(context.get('request'), 'user', None)
    if not user or not user.is_authenticated:
        return ''
    if user.branch:
        return user.branch.name
    return 'All Branches'


# ============================================================================
# Schedule-specific Permission Checks
# ============================================================================

@register.simple_tag(takes_context=True)
def can_edit_schedule_entry(context, schedule_entry):
    """
    Check if user can edit a specific schedule entry.
    Users with 'can_manage_own_schedule' can only edit their own schedules.
    Admins can edit any schedule.
    
    Usage:
        {% can_edit_schedule_entry schedule as can_edit %}
        {% if can_edit %}
            <button>Edit</button>
        {% endif %}
    """
    request = context.get('request')
    if not request or not request.user.is_authenticated:
        return False
    
    user = request.user
    
    # Superusers and users with schedule-management access can edit any schedule
    if user.is_superuser:
        return True

    if user.can_manage_other_schedules():
        return True

    if user.has_module_permission('schedule', 'EDIT'):
        return True

    # Users with manage_own_schedule can edit their own
    if user.has_special_permission('can_manage_own_schedule'):
        # Check if this is the user's own schedule
        if hasattr(schedule_entry, 'staff') and hasattr(schedule_entry.staff, 'user'):
            return schedule_entry.staff.user == user
    
    return False


@register.simple_tag(takes_context=True)
def can_delete_schedule_entry(context, schedule_entry):
    """
    Check if user can delete a specific schedule entry.
    Users with 'can_manage_own_schedule' can only delete their own schedules.
    Admins can delete any schedule.
    
    Usage:
        {% can_delete_schedule_entry schedule as can_delete %}
        {% if can_delete %}
            <button>Delete</button>
        {% endif %}
    """
    request = context.get('request')
    if not request or not request.user.is_authenticated:
        return False
    
    user = request.user
    
    # Superusers and users with schedule-management access can delete any schedule
    if user.is_superuser:
        return True

    if user.can_manage_other_schedules():
        return True

    if user.has_module_permission('schedule', 'DELETE'):
        return True

    # Users with manage_own_schedule can delete their own
    if user.has_special_permission('can_manage_own_schedule'):
        # Check if this is the user's own schedule
        if hasattr(schedule_entry, 'staff') and hasattr(schedule_entry.staff, 'user'):
            return schedule_entry.staff.user == user
    
    return False


@register.simple_tag(takes_context=True)
def can_create_own_schedule(context):
    """
    Check if user can create their own schedule entries.
    
    Usage:
        {% can_create_own_schedule as can_create %}
        {% if can_create %}
            <button>Add Schedule</button>
        {% endif %}
    """
    user = context.get('user') or getattr(context.get('request'), 'user', None)
    if not user or not user.is_authenticated:
        return False
    
    # Superusers and users with schedule-management access can always create
    if user.is_superuser:
        return True

    if user.can_manage_other_schedules():
        return True

    if user.has_module_permission('schedule', 'CREATE'):
        return True

    # Users with manage_own_schedule can create their own
    return user.has_special_permission('can_manage_own_schedule') or user.has_special_permission('can_manage_others_schedule')
