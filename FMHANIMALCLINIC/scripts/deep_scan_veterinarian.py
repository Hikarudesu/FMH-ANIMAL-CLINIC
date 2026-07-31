#!/usr/bin/env python
"""
Deep scan of Veterinarian role module assignments and permissions.
Identifies what modules the vet has and what notifications should be available.
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'FMHANIMALCLINIC.settings')
django.setup()

from django.contrib.auth import get_user_model
from accounts.models import Role, ModulePermission, Module
from notifications.models import Notification

User = get_user_model()

# Get veterinarian role
try:
    vet_role = Role.objects.get(code='veterinarian')
except Role.DoesNotExist:
    print("❌ Veterinarian role not found")
    exit(1)

print("=" * 80)
print("VETERINARIAN ROLE - DEEP SCAN")
print("=" * 80)
print(f"\nRole: Veterinarian")
print(f"Hierarchy Level: {vet_role.hierarchy_level}")

# Get all modules and their permissions for vet
vet_perms = ModulePermission.objects.filter(role=vet_role).select_related('module')

modules_with_perms = {}
for perm in vet_perms:
    mod_code = perm.module.code
    if mod_code not in modules_with_perms:
        modules_with_perms[mod_code] = {
            'name': perm.module.name,
            'permissions': []
        }
    modules_with_perms[mod_code]['permissions'].append(perm.permission_type)

print(f"\nModules Assigned ({len(modules_with_perms)}):")
for mod_code in sorted(modules_with_perms.keys()):
    mod_info = modules_with_perms[mod_code]
    perms = ', '.join(sorted(mod_info['permissions']))
    print(f"  ✓ {mod_code:20} ({mod_info['name']:30}) - {perms}")

# Map modules to notification types
notification_mapping = {
    'appointments': [
        'APPOINTMENT',
        'APPOINTMENT_CONFIRMED',
        'APPOINTMENT_CANCELLED',
        'APPOINTMENT_RESCHEDULED',
        'APPOINTMENT_REMINDER_1',
        'APPOINTMENT_REMINDER_2',
        'FOLLOW_UP',
        'FOLLOW_UP_OVERDUE',
    ],
    'inventory': [
        'INVENTORY_RESTOCK',
        'LOW_INVENTORY',
        'INVENTORY_EXPIRY_ALERT',
        'LOW_STOCK_ALERT',
        'PRODUCT_RESERVATION',
        'RESERVATION_APPROVED',
        'RESERVATION_READY',
        'RESERVATION_REJECTED',
    ],
    'medical_records': [
        'MEDICAL_RECORD_UPDATE',
    ],
    'patients': [
        # No notifications defined for patients module
    ],
    'diagnostics': [
        # No notifications defined for diagnostics module yet
    ],
}

print("\n" + "=" * 80)
print("EXPECTED NOTIFICATIONS FOR VET'S MODULES")
print("=" * 80)

expected_notif_types = set()
for mod_code in modules_with_perms.keys():
    if mod_code in notification_mapping:
        notif_types = notification_mapping[mod_code]
        print(f"\n{mod_code.upper()} → {len(notif_types)} notification types:")
        for notif in notif_types:
            print(f"  • {notif}")
            expected_notif_types.add(notif)
    else:
        print(f"\n{mod_code.upper()} → NO NOTIFICATIONS MAPPED")

print(f"\n\nTotal Expected Notification Types: {len(expected_notif_types)}")
print("Expected notification types:")
for notif in sorted(expected_notif_types):
    print(f"  • {notif}")

print("\n" + "=" * 80)
print("CURRENT NOTIFICATION FILTER MAPPING")
print("=" * 80)

# Check the actual filter mapping in views.py
print("\nReading notifications/views.py for vet filter mapping...")
try:
    with open('notifications/views.py', 'r') as f:
        content = f.read()
        if 'get_notification_type_to_module_mapping' in content:
            print("✓ Found get_notification_type_to_module_mapping() function")
            # Try to find veterinarian-specific mapping
            if "'veterinarian'" in content:
                print("✓ Found veterinarian-specific mapping references")
        else:
            print("⚠️  Could not find notification filter mapping function")
except Exception as e:
    print(f"❌ Error reading views.py: {e}")

print("\n" + "=" * 80)
print("CHECKING NOTIFICATION DELIVERY - WHERE VETS ARE NOTIFIED")
print("=" * 80)

# Check signals and utils for vet notifications
print("\nSearching for veterinarian notifications in code...")
files_to_check = [
    'notifications/signals.py',
    'notifications/utils.py',
]

for filename in files_to_check:
    print(f"\nChecking {filename}...")
    try:
        with open(filename, 'r') as f:
            content = f.read()
            if 'veterinarian' in content.lower():
                count = content.lower().count('veterinarian')
                print(f"  ✓ Found {count} reference(s) to 'veterinarian'")
                # Show some context
                lines = content.split('\n')
                for i, line in enumerate(lines):
                    if 'veterinarian' in line.lower():
                        print(f"     Line {i+1}: {line.strip()[:80]}")
            else:
                print(f"  ⚠️  No 'veterinarian' references found")
    except Exception as e:
        print(f"  ❌ Error: {e}")

print("\n" + "=" * 80)
print("SUMMARY")
print("=" * 80)
print(f"""
Veterinarian Role Analysis:
- Modules Assigned: {len(modules_with_perms)}
- Expected Notification Types: {len(expected_notif_types)}
- Modules with Notifications: {len([m for m in modules_with_perms.keys() if m in notification_mapping])}

Next Steps:
1. Get test vet user and check their notification filter
2. Verify notification types match assigned modules
3. Check if vet is receiving notifications from their modules
4. Clean up any incorrect/missing filters
""")
