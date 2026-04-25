"""Role-Based Access Control (RBAC) models for granular permissions."""
from django.db import models


# Modules reserved for superuser only — hidden from role creation/edit UI
SUPERUSER_ONLY_MODULES = [
    'settings',
    'notifications',
    'roles',
    'payroll',
    'soa',
    'stock_transfers',
    'reports',
    'analytics',        # Analytics is for superuser only
    'activity_logs',    # Activity logs is for superuser only
]

# Modules hidden from module permissions UI (handled differently)
# These are either auto-created, view-only, or handled by special permissions
HIDDEN_FROM_MODULE_PERMISSIONS = [
    'dashboard',          # Moved to special permissions as "Staff Dashboard"
    'admin_dashboard',    # Moved to special permissions as "Admin Dashboard"
    'staff',              # Only viewable/editable, handled separately
    'schedule',           # Replaced by "Manage Own Schedule" special permission
    'branches',           # View only, admin-controlled
    'user_portal',        # Auto-created with user account
    'pos',                # Moved to special permissions
    'stock_monitor',      # Moved to special permissions (branch-restricted)
]

# Modules that support full CRUD operations with branch restriction
CRUD_MODULES = [
    'appointments',
    'patients',
    'medical_records',
    'ai_diagnostics',    # Note: No EDIT for AI diagnostics
    'clinic_services',
    'inventory',
]

# Special permission codes
class SpecialPermissionCodes:
    """Constants for special permission codes."""
    STAFF_DASHBOARD = 'can_access_staff_dashboard'
    ADMIN_DASHBOARD = 'can_access_admin_dashboard'
    POINT_OF_SALE = 'can_access_pos'
    MANAGE_OWN_SCHEDULE = 'can_manage_own_schedule'
    VIEW_OWN_PAYSLIPS = 'can_view_own_payslips'
    STOCK_MONITOR = 'can_access_stock_monitor'


class Module(models.Model):
    """
    Represents a module/section in the system.
    Each module can have associated permissions.
    """
    # Module codes for programmatic access
    DASHBOARD = 'dashboard'
    APPOINTMENTS = 'appointments'
    PATIENTS = 'patients'
    MEDICAL_RECORDS = 'medical_records'
    AI_DIAGNOSTICS = 'ai_diagnostics'
    POS = 'pos'
    CLINIC_SERVICES = 'clinic_services'
    SOA = 'soa'
    PAYROLL = 'payroll'
    STAFF = 'staff'
    SCHEDULE = 'schedule'
    BRANCHES = 'branches'
    INQUIRIES = 'inquiries'
    INVENTORY = 'inventory'
    STOCK_MONITOR = 'stock_monitor'
    STOCK_TRANSFERS = 'stock_transfers'
    ANALYTICS = 'analytics'
    NOTIFICATIONS = 'notifications'
    ACTIVITY_LOGS = 'activity_logs'
    SETTINGS = 'settings'
    ROLES = 'roles'

    MODULE_CHOICES = [
        (DASHBOARD, 'Dashboard'),
        (APPOINTMENTS, 'Appointments'),
        (PATIENTS, 'Patients'),
        (MEDICAL_RECORDS, 'Medical Records'),
        (AI_DIAGNOSTICS, 'AI Diagnostics'),
        (POS, 'Point of Sale'),
        (CLINIC_SERVICES, 'Clinic Services'),
        (SOA, 'Statement of Account'),
        (PAYROLL, 'Payroll'),
        (STAFF, 'Staff'),
        (SCHEDULE, 'Schedule'),
        (BRANCHES, 'Branches'),
        (INQUIRIES, 'Inquiries'),
        (INVENTORY, 'Inventory'),
        (STOCK_MONITOR, 'Stock Monitor'),
        (STOCK_TRANSFERS, 'Stock Transfers'),
        (ANALYTICS, 'Analytics'),
        (NOTIFICATIONS, 'Notifications'),
        (ACTIVITY_LOGS, 'Activity Logs'),
        (SETTINGS, 'Settings'),
        (ROLES, 'Role Management'),
    ]

    code = models.CharField(max_length=50, unique=True, choices=MODULE_CHOICES)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=50, blank=True, help_text='Boxicons class name')
    url_name = models.CharField(max_length=100, blank=True, help_text='Django URL name')
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='children',
        help_text='Parent module for submenu grouping'
    )
    display_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['display_order', 'name']
        verbose_name = 'Module'
        verbose_name_plural = 'Modules'

    def __str__(self):
        return self.name


class ModulePermission(models.Model):
    """
    Represents a specific permission for a module.
    Links Role -> Module with specific permission levels.
    """
    class PermissionType(models.TextChoices):
        VIEW = 'VIEW', 'View'
        CREATE = 'CREATE', 'Create'
        EDIT = 'EDIT', 'Edit'
        DELETE = 'DELETE', 'Delete'
        MANAGE = 'MANAGE', 'Full Management'  # Admin-level access

    role = models.ForeignKey(
        'Role',
        on_delete=models.CASCADE,
        related_name='module_permissions'
    )
    module = models.ForeignKey(
        Module,
        on_delete=models.CASCADE,
        related_name='role_permissions'
    )
    permission_type = models.CharField(
        max_length=20,
        choices=PermissionType.choices,
        default=PermissionType.VIEW
    )
    restrict_to_branch = models.BooleanField(
        default=False,
        help_text='If True, users see only their branch data for this module'
    )

    class Meta:
        unique_together = ['role', 'module', 'permission_type']
        verbose_name = 'Module Permission'
        verbose_name_plural = 'Module Permissions'

    def __str__(self):
        suffix = ' [Branch]' if self.restrict_to_branch else ''
        return f"{self.role.name} - {self.module.name} ({self.permission_type}){suffix}"


class Role(models.Model):
    """
    Custom role with configurable permissions.
    Replaces the hardcoded User.Role choices with dynamic roles.
    """
    # Default role codes for seeding
    SUPERADMIN = 'superadmin'
    BRANCH_ADMIN = 'branch_admin'
    VET = 'veterinarian'
    RECEPTIONIST = 'receptionist'
    VET_ASSISTANT = 'vet_assistant'

    name = models.CharField(max_length=100, unique=True)
    code = models.SlugField(max_length=50, unique=True)
    description = models.TextField(blank=True)

    # Module access is defined through ModulePermission
    modules = models.ManyToManyField(
        Module,
        through=ModulePermission,
        related_name='roles'
    )

    # Role hierarchy level (higher = more permissions)
    hierarchy_level = models.PositiveIntegerField(
        default=0,
        help_text='Higher level = more authority (0=basic, 10=admin)'
    )

    # Can this role access the admin portal?
    is_staff_role = models.BooleanField(
        default=True,
        help_text='If True, users with this role access the admin portal'
    )

    # Is this a system role (cannot be deleted)?
    is_system_role = models.BooleanField(
        default=False,
        help_text='System roles cannot be deleted'
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-hierarchy_level', 'name']
        verbose_name = 'Role'
        verbose_name_plural = 'Roles'

    def __str__(self):
        return self.name

    def clean(self):
        """Validate role data."""
        if self.is_system_role and not self.pk:
            # New system roles can only be created through migrations
            existing = Role.objects.filter(code=self.code).exists()
            if not existing:
                pass  # Allow creation
        super().clean()

    def has_module_permission(self, module_code, permission_type=None):
        """
        Check if this role has access to a module.

        Args:
            module_code: The Module code (e.g., 'appointments')
            permission_type: Optional specific permission (VIEW, CREATE, etc.)
                           If None, checks for any permission

        Returns:
            bool: True if the role has the requested permission
        """
        # Admin roles have full access
        if self.hierarchy_level >= 10:
            return True

        query = self.module_permissions.filter(module__code=module_code)
        if permission_type:
            query = query.filter(permission_type=permission_type)
        return query.exists()

    def get_module_permissions(self, module_code):
        """
        Get all permission types this role has for a module.

        Returns:
            list: List of permission type strings
        """
        if self.hierarchy_level >= 10:
            return [p[0] for p in ModulePermission.PermissionType.choices]

        return list(
            self.module_permissions
            .filter(module__code=module_code)
            .values_list('permission_type', flat=True)
        )

    def get_accessible_modules(self):
        """
        Get all modules this role can access.

        Returns:
            QuerySet: Module objects
        """
        if self.hierarchy_level >= 10:
            return Module.objects.filter(is_active=True)

        module_ids = (
            self.module_permissions
            .values_list('module_id', flat=True)
            .distinct()
        )
        return Module.objects.filter(id__in=module_ids, is_active=True)

    def get_navigation_modules(self):
        """Get modules this role should see in navigation."""
        return self.get_accessible_modules()

    def is_module_branch_restricted(self, module_code):
        """
        Check if this role is branch-restricted for a specific module.

        Returns:
            bool: True if the role should only see own-branch data for this module
        """
        if self.hierarchy_level >= 10:
            return False

        # Check if ANY permission for this module has restrict_to_branch=True
        return self.module_permissions.filter(
            module__code=module_code,
            restrict_to_branch=True
        ).exists()


class SpecialPermission(models.Model):
    """
    Special permissions for edge cases not covered by module permissions.
    Examples: 'can_view_own_payslips', 'can_manage_own_schedule'
    """
    code = models.CharField(max_length=100, unique=True)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)

    class Meta:
        verbose_name = 'Special Permission'
        verbose_name_plural = 'Special Permissions'

    def __str__(self):
        return self.name


class RoleSpecialPermission(models.Model):
    """Links roles to special permissions."""
    role = models.ForeignKey(
        Role,
        on_delete=models.CASCADE,
        related_name='special_permissions'
    )
    permission = models.ForeignKey(
        SpecialPermission,
        on_delete=models.CASCADE,
        related_name='role_assignments'
    )

    class Meta:
        unique_together = ['role', 'permission']
        verbose_name = 'Role Special Permission'
        verbose_name_plural = 'Role Special Permissions'

    def __str__(self):
        return f"{self.role.name} - {self.permission.name}"
