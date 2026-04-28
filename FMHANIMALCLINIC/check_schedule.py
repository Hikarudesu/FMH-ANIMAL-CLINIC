#!/usr/bin/env python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'FMHANIMALCLINIC.settings')
django.setup()

from accounts.rbac_models import Module
from accounts.models import User

print("=" * 70)
print("CHECKING SCHEDULE MODULE AND NAV VISIBILITY")
print("=" * 70)

# Check if schedule module exists
schedule_module = Module.objects.filter(code='schedule').first()
if schedule_module:
    print(f"\n✓ Schedule module exists:")
    print(f"  - Active: {schedule_module.is_active}")
    print(f"  - In HIDDEN_FROM_MODULE_PERMISSIONS: {'schedule' in ['dashboard', 'admin_dashboard', 'staff', 'schedule', 'branches', 'user_portal', 'pos', 'stock_monitor']}")

# Get veterinarian with schedule permission
vet = User.objects.filter(assigned_role__code='veterinarian').first()
if vet:
    print(f"\n✓ Testing veterinarian: {vet.email}")
    
    # Check module permission
    has_module_perm = vet.has_navigation_module_access('schedule')
    print(f"  - has_navigation_module_access('schedule'): {has_module_perm}")
    
    # Check special permissions
    has_own = vet.has_navigation_special_permission('can_manage_own_schedule')
    has_others = vet.has_navigation_special_permission('can_manage_others_schedule')
    print(f"  - has_nav_special_permission('can_manage_own_schedule'): {has_own}")
    print(f"  - has_nav_special_permission('can_manage_others_schedule'): {has_others}")
    
    print(f"\n  Result: Template should show Schedule because:")
    print(f"  - has_own or has_others = {has_own or has_others}")

print("\n" + "=" * 70)
