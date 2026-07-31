"""Models for the accounts app."""
# pylint: disable=no-member,unused-argument

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver

from utils.validators import validate_image_file, IMAGE_UPLOAD_HELP_TEXT

OVERSEER_HIDDEN_NAV_MODULES = {
    'patients',
    'appointments',
    'medical_records',
    'ai_diagnostics',
    'inquiries',
    'pos',
    'reports',
    'soa',
}

OVERSEER_REQUIRED_NAV_MODULES = {
    'schedule',
    'clinic_services',
}


class User(AbstractUser):
    """Custom user model with role-based access control."""

 
    # New RBAC role assignment
    assigned_role = models.ForeignKey(
        'accounts.Role',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='users',
        help_text='Custom role with granular permissions'
    )

    branch = models.ForeignKey(
        'branches.Branch',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='branch_users',
        help_text='The branch this user belongs to.',
    )
    profile_picture = models.ImageField(
        upload_to='profiles/',
        blank=True,
        null=True,
        validators=[validate_image_file],
        help_text=IMAGE_UPLOAD_HELP_TEXT
    )
    phone_number = models.CharField(max_length=20, blank=True)
    address = models.TextField(
        blank=True, help_text='Full address of the pet owner')

    # ── helper properties ──────────────────────────────────
    def is_admin_role(self):
        """Returns True if the user has superadmin-level assigned role (hierarchy >= 10)."""
        if self.is_superuser:
            return True
        if self.assigned_role:
            return getattr(self.assigned_role, 'hierarchy_level', 0) >= 10
        return False

    def is_branch_admin(self):
        """Returns True if the user has branch admin or higher role (hierarchy >= 8)."""
        if self.is_superuser:
            return True
        if self.assigned_role:
            return getattr(self.assigned_role, 'hierarchy_level', 0) >= 8
        return False

    def is_clinic_staff(self):
        """Returns True if the user needs access to the admin portal."""
        if self.is_superuser:
            return True
        if self.assigned_role:
            return self.assigned_role.is_staff_role
        return False

    def is_pet_owner(self):
        """Returns True if the user is a pet owner (not a staff member)."""
        if self.is_superuser:
            return False
        if self.assigned_role:
            return not self.assigned_role.is_staff_role
        return True  # Default to pet owner for safety if no role assigned

    def has_module_permission(self, module_code, permission_type=None):
        """
        Check if user has permission for a specific module.

        Args:
            module_code: The Module code (e.g., 'appointments')
            permission_type: Optional specific permission ('VIEW', 'CREATE', etc.)

        Returns:
            bool: True if user has the permission
        """
        if self.is_superuser:
            return True

        if self.assigned_role:
            return self.assigned_role.has_module_permission(module_code, permission_type)

        return False
    def has_special_permission(self, permission_code):
        """
        Check if user has a special permission.

        Args:
            permission_code: The SpecialPermission code

        Returns:
            bool: True if user has the permission
        """
        if self.is_superuser:
            return True

        if self.assigned_role:
            return self.assigned_role.special_permissions.filter(
                permission__code=permission_code
            ).exists()

        return False

    def can_manage_other_schedules(self):
        """Return True when the user can manage schedules for other staff."""
        if self.is_superuser:
            return True

        if self.assigned_role and getattr(self.assigned_role, 'hierarchy_level', 0) >= 8:
            return True

        return self.has_special_permission('can_manage_others_schedule')

    def has_navigation_module_access(self, module_code):
        """Navigation-only module visibility check."""
        if self.is_superuser and module_code in OVERSEER_HIDDEN_NAV_MODULES:
            return False
        if self.is_superuser and module_code in OVERSEER_REQUIRED_NAV_MODULES:
            return True
        return self.has_module_permission(module_code)

    def has_navigation_special_permission(self, permission_code):
        """Navigation-only special permission visibility check."""
        if self.is_superuser and permission_code == 'can_access_pos':
            return False
        return self.has_special_permission(permission_code)

    def get_accessible_modules(self):
        """
        Get all modules this user can access.

        Returns:
            QuerySet or list: Module objects
        """
        from accounts.rbac_models import Module
        if self.is_superuser:
            return Module.objects.filter(is_active=True)

        if self.assigned_role:
            return self.assigned_role.get_accessible_modules()

        return Module.objects.none()
    def is_branch_restricted(self, module_code=None):
        """
        Check if user data access is restricted to their branch.

        Args:
            module_code: Optional module code for per-module check.
                        If None, returns True if ANY module is restricted.

        Returns:
            bool: True if user can only see their branch's data
        """
        if self.is_superuser:
            return False

        if self.assigned_role:
            if module_code:
                return self.assigned_role.is_module_branch_restricted(module_code)
            # Backward compat: check if any module permission has branch restriction
            return self.assigned_role.module_permissions.filter(
                restrict_to_branch=True
            ).exists()

        return True  # Default to restricted if no explicit role

    def is_module_branch_restricted(self, module_code):
        """
        Check if user is branch-restricted for a specific module.

        Args:
            module_code: The module code (e.g., 'appointments')

        Returns:
            bool: True if user can only see their branch's data for this module
        """
        if self.is_superuser:
            return False

        if self.assigned_role:
            return self.assigned_role.is_module_branch_restricted(module_code)

        return True  # Default to restricted if no explicit role
    def get_display_role(self):
        """
        Get the display name for the user's role.

        Returns:
            str: Role display name
        """
        if self.is_superuser:
            return 'Overseer'
        if self.assigned_role:
            return self.assigned_role.name
        return 'Pet Owner'

    def save(self, *args, **kwargs):
        """Save user."""
        super().save(*args, **kwargs)

    class Meta:
        """Meta options for User model."""
        ordering = ['username']

    def __str__(self):
        return f'{self.username} ({self.get_display_role()})'


class UserActivity(models.Model):
    """Logs recent actions performed by the user."""
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='recent_activities')
    action = models.CharField(max_length=50)  # e.g., 'Created', 'Updated'
    object_name = models.CharField(max_length=200)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        """Meta options for UserActivity model."""
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.user.username} - {self.action} {self.object_name}"


# Signals for UserActivity


@receiver(post_save, sender='patients.Pet')
def log_pet_activity(sender, instance, created, **kwargs):
    """Log an activity when a Pet record is created or updated."""
    if hasattr(instance, 'owner') and instance.owner:
        action = 'Created Pet' if created else 'Updated Pet'
        UserActivity.objects.create(
            user=instance.owner,
            action=action,
            object_name=instance.name
        )


@receiver(post_save, sender='appointments.Appointment')
def log_appointment_activity(sender, instance, created, **kwargs):
    """Log an activity when an Appointment is created or updated."""
    if hasattr(instance, 'user') and instance.user:
        action = 'Created Appointment' if created else 'Updated Appointment'
        UserActivity.objects.create(
            user=instance.user,
            action=action,
            object_name=f"Appointment on {instance.appointment_date}"
        )


class ActivityLog(models.Model):
    """
    Comprehensive activity logging for all system actions.
    Supports multiple categories and detailed action tracking.
    """
    class Category(models.TextChoices):
        """Categories for grouping activity logs."""
        STOCK = 'STOCK', 'Stock Management'
        USER = 'USER', 'User Management'
        SYSTEM = 'SYSTEM', 'System Settings'
        APPOINTMENT = 'APPOINTMENT', 'Appointment'
        MEDICAL = 'MEDICAL', 'Medical Records'
        BILLING = 'BILLING', 'Billing'
        POS = 'POS', 'Point of Sale'
        PATIENT = 'PATIENT', 'Patient'
        PAYROLL = 'PAYROLL', 'Payroll'
        STAFF = 'STAFF', 'Staff'

    class ActionType(models.TextChoices):
        """Types of actions performed."""
        CREATE = 'CREATE', 'Create'
        UPDATE = 'UPDATE', 'Update'
        DELETE = 'DELETE', 'Delete'
        VIEW = 'VIEW', 'View'
        LOGIN = 'LOGIN', 'Login'
        LOGOUT = 'LOGOUT', 'Logout'
        APPROVE = 'APPROVE', 'Approve'
        REJECT = 'REJECT', 'Reject'
        EXPORT = 'EXPORT', 'Export'
        OTHER = 'OTHER', 'Other'

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='system_logs')
    action = models.CharField(max_length=100)
    category = models.CharField(
        max_length=50, choices=Category.choices, default=Category.SYSTEM)
    action_type = models.CharField(
        max_length=20, choices=ActionType.choices, default=ActionType.OTHER)
    branch = models.ForeignKey(
        'branches.Branch', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='activity_logs'
    )
    details = models.TextField(blank=True, null=True)
    object_type = models.CharField(max_length=100, blank=True, null=True)
    object_id = models.PositiveIntegerField(blank=True, null=True)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        """Meta options for ActivityLog."""
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['category', '-timestamp']),
            models.Index(fields=['user', '-timestamp']),
            models.Index(fields=['action_type', '-timestamp']),
            models.Index(fields=['branch', '-timestamp']),
        ]

    def __str__(self):
        return f"[{self.category}] {self.user.username}: {self.action}"


def log_activity(user, action, category, action_type=ActivityLog.ActionType.OTHER, 
                 branch=None, details='', object_type='', object_id=None, ip_address=None):
    """Utility function to log activity."""
    try:
        ActivityLog.objects.create(
            user=user,
            action=action,
            category=category,
            action_type=action_type,
            branch=branch or getattr(user, 'branch', None),
            details=details,
            object_type=object_type,
            object_id=object_id,
            ip_address=ip_address
        )
    except Exception as e:
        print(f"Error logging activity: {e}")


# NOTE: Signal handlers for user_logged_in and post_save(User) are defined
# in accounts/signals.py to avoid duplicate logging. Do NOT add handlers here.


# ── Auto-create PetOwner profile for non-staff users ──────────────────────────

@receiver(post_save, sender='accounts.User')
def create_pet_owner_profile(sender, instance, created, **kwargs):
    """Automatically create a PetOwner profile for non-staff users."""
    if instance.is_superuser:
        return
    # Only create for pet owners (no staff role)
    if instance.is_pet_owner():
        from accounts.pet_owner_models import PetOwner
        PetOwner.objects.get_or_create(user=instance)
