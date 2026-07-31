#!/usr/bin/env python
"""Final verification of receptionist notification system."""

import os
import sys
import django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'FMHANIMALCLINIC.settings')
django.setup()

from django.contrib.auth import get_user_model
from accounts.rbac_models import Role
from notifications.views import get_allowed_notification_types_for_user
from notifications.models import Notification

User = get_user_model()

print("\n" + "="*80)
print("RECEPTIONIST NOTIFICATION SYSTEM - FINAL VERIFICATION")
print("="*80)

# Get receptionist role
receptionist_role = Role.objects.get(code='receptionist')
print(f"\nRole: {receptionist_role.name}")
print(f"Hierarchy Level: {receptionist_role.hierarchy_level}")

# Get all accessible modules
modules = list(receptionist_role.module_permissions.values_list('module__code', flat=True).distinct())
print(f"\nAccessible Modules ({len(modules)}):")
for mod in sorted(modules):
    print(f"  - {mod}")

# Get a receptionist user
receptionist_user = User.objects.filter(assigned_role__code='receptionist').first()

if receptionist_user:
    print(f"\nTest User: {receptionist_user.username}")
    print(f"Branch: {receptionist_user.branch}")
    
    # Get allowed notification types
    allowed_types = get_allowed_notification_types_for_user(receptionist_user)
    
    print(f"\nNotification Types in Filter ({len(allowed_types)}):")
    
    # Categorize by type
    appointments = []
    inventory = []
    other = []
    
    for code, label in allowed_types:
        if 'APPOINTMENT' in code or 'FOLLOW_UP' in code:
            appointments.append((code, label))
        elif 'INVENTORY' in code or 'STOCK' in code or 'PRODUCT_RESERVATION' in code:
            inventory.append((code, label))
        else:
            other.append((code, label))
    
    print(f"\n  Appointments ({len(appointments)}):")
    for code, label in sorted(appointments):
        print(f"    - {code}")
    
    print(f"\n  Inventory ({len(inventory)}):")
    for code, label in sorted(inventory):
        print(f"    - {code}")
    
    print(f"\n  Other ({len(other)}):")
    for code, label in sorted(other):
        print(f"    - {code}")
    
    # Verify exclusions
    print(f"\n\nVerification of Exclusions:")
    should_not_see = ['INQUIRY_NEW', 'PAYROLL_GENERATED', 'MEDICAL_RECORD_UPDATE', 'STOCK_TRANSFER_REQUESTED']
    all_codes = [code for code, label in allowed_types]
    
    all_ok = True
    for notif_type in should_not_see:
        if notif_type in all_codes:
            print(f"  [ERROR] {notif_type} should NOT be visible")
            all_ok = False
        else:
            print(f"  [OK] {notif_type} correctly excluded")
    
    if all_ok:
        print(f"\n[SUCCESS] All notification filters are correctly configured!")
    else:
        print(f"\n[FAILED] Some notification types are incorrectly included")
else:
    print("No receptionist user found in database")

print("\n" + "="*80)
