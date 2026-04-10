"""Admin configuration for the accounts app."""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.db.models import Q

from .models import User
from .rbac_models import Module, ModulePermission, Role, RoleSpecialPermission, SpecialPermission
from .pet_owner_models import PetOwner
from .otp_models import OTPToken


class PetOwnerInline(admin.StackedInline):
    """Inline for PetOwner profile within User admin."""
    model = PetOwner
    can_delete = False
    verbose_name = 'Pet Owner Profile'
    verbose_name_plural = 'Pet Owner Profile'
    fk_name = 'user'
    extra = 0
    fields = ('emergency_contact_name', 'emergency_contact_phone',
              'preferred_communication', 'notes')
class StaffUser(User):
    """Proxy model to rename 'Users' to 'Staff' in the admin panel."""
    class Meta:
        """Meta options for StaffUser proxy model."""
        proxy = True
        verbose_name = 'Staff Member'
        verbose_name_plural = 'Staff'


@admin.register(StaffUser)
class UserAdmin(BaseUserAdmin):
    """Custom admin for the User model with role and branch fields, restricted to staff."""

    list_display = (
        'username', 'email', 'first_name', 'last_name',
        'assigned_role', 'branch', 'is_active'
    )
    list_filter = ('assigned_role', 'branch', 'is_active', 'is_staff')
    search_fields = ('username', 'email', 'first_name', 'last_name')

    # Add role & branch to the existing fieldsets
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Clinic Info', {
            'fields': ('assigned_role', 'branch', 'phone_number', 'profile_picture')
        }),
    )

    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ('Clinic Info', {'fields': ('assigned_role', 'branch', 'phone_number')}),
    )

    def get_queryset(self, request):
        """Show only staff members (exclude pet owners)."""
        qs = super().get_queryset(request)
        return qs.filter(
            Q(is_superuser=True) |
            Q(assigned_role__is_staff_role=True) |
            Q(is_staff=True)
        ).distinct()


class ModulePermissionInline(admin.TabularInline):
    """Inline for managing module permissions within Role admin."""
    model = ModulePermission
    extra = 1
    autocomplete_fields = ['module']


class RoleSpecialPermissionInline(admin.TabularInline):
    """Inline for managing special permissions within Role admin."""
    model = RoleSpecialPermission
    extra = 1
    autocomplete_fields = ['permission']


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    """Admin for the Role model."""
    list_display = (
        'name', 'code', 'hierarchy_level', 'is_staff_role', 'is_system_role', 'user_count'
    )
    list_filter = ('is_staff_role', 'is_system_role', 'hierarchy_level')
    search_fields = ('name', 'code', 'description')
    prepopulated_fields = {'code': ('name',)}
    readonly_fields = ('created_at', 'updated_at')
    inlines = [ModulePermissionInline, RoleSpecialPermissionInline]

    @admin.display(description='Users')
    def user_count(self, obj):
        """Display the number of users with this role."""
        return obj.users.count()

    def has_delete_permission(self, request, obj=None):
        """Prevent deletion of system roles."""
        if obj and obj.is_system_role:
            return False
        return super().has_delete_permission(request, obj)


@admin.register(Module)
class ModuleAdmin(admin.ModelAdmin):
    """Admin for the Module model."""
    list_display = ('name', 'code', 'icon', 'display_order', 'is_active', 'parent')
    list_filter = ('is_active', 'parent')
    search_fields = ('name', 'code', 'description')
    ordering = ('display_order', 'name')


@admin.register(SpecialPermission)
class SpecialPermissionAdmin(admin.ModelAdmin):
    """Admin for the SpecialPermission model."""
    list_display = ('name', 'code', 'description')
    search_fields = ('name', 'code', 'description')


@admin.register(ModulePermission)
class ModulePermissionAdmin(admin.ModelAdmin):
    """Admin for the ModulePermission model."""
    list_display = ('role', 'module', 'permission_type')
    list_filter = ('role', 'module', 'permission_type')
    search_fields = ('role__name', 'module__name')


@admin.register(PetOwner)
class PetOwnerAdmin(admin.ModelAdmin):
    """Admin for viewing/managing Pet Owner profiles."""
    list_display = (
        'full_name', 'email', 'phone', 'preferred_communication', 'pet_count', 'updated_at'
    )
    list_filter = ('preferred_communication', 'created_at')
    search_fields = ('user__first_name', 'user__last_name', 'user__email', 'user__username')
    readonly_fields = ('user', 'created_at', 'updated_at')
    fieldsets = (
        ('Linked Account', {'fields': ('user',)}),
        ('Emergency Contact', {'fields': ('emergency_contact_name', 'emergency_contact_phone')}),
        ('Preferences', {'fields': ('preferred_communication',)}),
        ('Notes', {'fields': ('notes',)}),
        ('Timestamps', {'fields': ('created_at', 'updated_at'), 'classes': ('collapse',)}),
    )


@admin.register(OTPToken)
class OTPTokenAdmin(admin.ModelAdmin):
    """Admin for viewing OTP tokens (read-only for security)."""
    list_display = ('user', 'otp_code', 'created_at', 'expires_at', 'is_used', 'is_still_valid')
    list_filter = ('is_used', 'created_at')
    search_fields = ('user__username', 'user__email')
    readonly_fields = ('user', 'otp_code', 'created_at', 'expires_at', 'is_used')

    def is_still_valid(self, obj):
        """Show if the OTP is still valid."""
        return obj.is_valid()
    is_still_valid.boolean = True

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
