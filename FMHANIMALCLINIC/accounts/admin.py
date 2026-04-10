from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User
from .rbac_models import Module, ModulePermission, Role, RoleSpecialPermission, SpecialPermission


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Custom admin for the User model with role and branch fields."""

    list_display = ('username', 'email', 'first_name', 'last_name', 'assigned_role', 'branch', 'is_active')
    list_filter = ('assigned_role', 'branch', 'is_active', 'is_staff')
    search_fields = ('username', 'email', 'first_name', 'last_name')

    # Add role & branch to the existing fieldsets
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Clinic Info', {'fields': ('assigned_role', 'branch', 'phone_number', 'profile_picture')}),
    )

    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ('Clinic Info', {'fields': ('assigned_role', 'branch', 'phone_number')}),
    )


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
    list_display = ('name', 'code', 'hierarchy_level', 'is_staff_role', 'is_system_role', 'user_count')
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

