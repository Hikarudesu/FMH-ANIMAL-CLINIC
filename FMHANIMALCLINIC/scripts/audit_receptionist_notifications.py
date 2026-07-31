#!/usr/bin/env python
"""
Comprehensive audit of receptionist notification coverage.
Checks that EVERY notification type the receptionist should receive is actually being sent.
"""
import os
import django
import sys

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'FMHANIMALCLINIC.settings')
django.setup()

from django.contrib.auth import get_user_model
from notifications.models import Notification
from accounts.models import ModulePermission

User = get_user_model()

# Get receptionist role and their module permissions
receptionist = None
try:
    from accounts.models import Role
    receptionist = Role.objects.get(code='receptionist')
except:
    print("❌ Receptionist role not found")
    sys.exit(1)

# Get all modules assigned to receptionist
receptionist_modules = set(
    ModulePermission.objects.filter(
        role=receptionist
    ).values_list('module__code', flat=True).distinct()
)

print("=" * 80)
print("RECEPTIONIST NOTIFICATION AUDIT")
print("=" * 80)
print(f"\nReceptionist Modules ({len(receptionist_modules)}):")
for mod in sorted(receptionist_modules):
    print(f"  ✓ {mod}")

# Define what notifications SHOULD exist for each module based on business logic
EXPECTED_NOTIFICATIONS = {
    'appointments': {
        'types': [
            'APPOINTMENT',
            'APPOINTMENT_CONFIRMED',
            'APPOINTMENT_CANCELLED',
            'APPOINTMENT_RESCHEDULED',
            'FOLLOW_UP',
            'FOLLOW_UP_OVERDUE',
        ],
        'reason': 'Receptionists book and manage appointments'
    },
    'inventory': {
        'types': [
            'INVENTORY_RESTOCK',
            'LOW_INVENTORY',
            'INVENTORY_EXPIRY_ALERT',
            'LOW_STOCK_ALERT',
            'PRODUCT_RESERVATION',
        ],
        'reason': 'Receptionists may need inventory alerts'
    },
    'reservations': {
        'types': [
            'RESERVATION_APPROVED',
            'RESERVATION_READY',
            'RESERVATION_REJECTED',
        ],
        'reason': 'Receptionists manage product reservations'
    },
    'inquiries': {
        'types': [
            'INQUIRY_NEW',
            'INQUIRY_RESPONDED',
            'INQUIRY_ARCHIVED',
        ],
        'reason': 'Receptionists may field inquiries'
    },
    'soa': {
        'types': [
            'STATEMENT_RELEASED',
        ],
        'reason': 'Receptionists need to communicate SOA to customers'
    },
    'pos': {
        'types': [
            'STATEMENT_RELEASED',  # When sales/statements are created
        ],
        'reason': 'Receptionists may ring up sales'
    },
    'clinic_services': {
        'types': [],  # No notifications defined yet
        'reason': 'Receptionists view/promote services'
    },
    'patients': {
        'types': [],  # No notifications defined yet
        'reason': 'Receptionists view/create patient records'
    },
}

# Check what's currently being sent to receptionists
print("\n" + "=" * 80)
print("CURRENT NOTIFICATION COVERAGE BY SOURCE")
print("=" * 80)

notification_coverage = {
    'APPOINTMENTS': {
        'send_locations': [
            '✓ notifications/signals.py - create_appointment_notification()',
            '✓ notifications/utils.py - notify_staff_appointment_status_change()',
        ],
        'receptionist_included': True,
    },
    'INVENTORY': {
        'send_locations': [
            '✓ notifications/signals.py - create_low_inventory_notification()',
            '✓ inventory/expiry_alerts.py - run_inventory_expiry_alert_job()',
        ],
        'receptionist_included': True,
    },
    'INQUIRIES': {
        'send_locations': [
            '❌ notifications/utils.py - notify_inquiry_received() - ONLY superadmins',
            '❌ notifications/utils.py - notify_inquiry_responded() - ONLY superadmins',
            '❌ notifications/utils.py - notify_inquiry_archived() - ONLY superadmins',
        ],
        'receptionist_included': False,
        'issue': 'Inquiry notifications only go to superadmins, not receptionists',
    },
    'RESERVATIONS': {
        'send_locations': [
            '❌ NO HANDLER FOUND - RESERVATION_APPROVED/READY/REJECTED never created',
        ],
        'receptionist_included': False,
        'issue': 'Reservation notifications defined but never actually sent anywhere',
    },
    'SOA/STATEMENT': {
        'send_locations': [
            '⚠️  notifications/utils.py - notify_statement_released() - ONLY customer notified',
            '   pos/services.py calls notify_statement_released(statement)',
        ],
        'receptionist_included': False,
        'issue': 'Statement notifications only go to customer, not receptionists',
    },
    'APPOINTMENTS_REMINDER': {
        'send_locations': [
            '❌ APPOINTMENT_REMINDER_1 and APPOINTMENT_REMINDER_2 - NO HANDLER',
        ],
        'receptionist_included': False,
        'issue': 'Reminder notifications are defined but no job/signal creates them',
    },
}

for notif_type, info in notification_coverage.items():
    status = "✓" if info['receptionist_included'] else "❌"
    print(f"\n{status} {notif_type}")
    for location in info['send_locations']:
        print(f"   {location}")
    if 'issue' in info:
        print(f"   ⚠️  ISSUE: {info['issue']}")

print("\n" + "=" * 80)
print("SUMMARY OF GAPS")
print("=" * 80)

gaps = []

# Check expectations vs reality
for module, expected in EXPECTED_NOTIFICATIONS.items():
    if module not in receptionist_modules:
        gaps.append(f"⚠️  Module '{module}' is assigned to receptionist but missing from database")
        continue
    
    for notif_type in expected['types']:
        if notif_type in ['INQUIRY_NEW', 'INQUIRY_RESPONDED', 'INQUIRY_ARCHIVED']:
            gaps.append(f"❌ {notif_type} - Created but ONLY for superadmins, not receptionists")
        elif notif_type in ['RESERVATION_APPROVED', 'RESERVATION_READY', 'RESERVATION_REJECTED']:
            gaps.append(f"❌ {notif_type} - NEVER CREATED anywhere in codebase")
        elif notif_type == 'STATEMENT_RELEASED':
            gaps.append(f"⚠️  {notif_type} - Created but ONLY for customer, not receptionists")
        elif notif_type in ['APPOINTMENT_REMINDER_1', 'APPOINTMENT_REMINDER_2']:
            gaps.append(f"❌ {notif_type} - Defined but NO JOB creates these reminder notifications")

if gaps:
    print("\n🔴 CRITICAL ISSUES:\n")
    for gap in sorted(set(gaps)):
        print(f"  {gap}")
else:
    print("\n✓ All notifications are properly configured!")

print("\n" + "=" * 80)
print("RECOMMENDATIONS")
print("=" * 80)
print("""
1. FIX INQUIRY NOTIFICATIONS
   - Modify notify_inquiry_received(), notify_inquiry_responded(), notify_inquiry_archived()
   - Change from _notify_superadmins() to notify_role_users('receptionist')
   - Or create both: notify superadmins AND receptionists

2. FIX STATEMENT/SOA NOTIFICATIONS
   - Modify notify_statement_released() to also notify receptionists
   - Currently only customer is notified

3. ADD RESERVATION NOTIFICATIONS
   - Create signal handlers or update inventory models to trigger notifications
   - for RESERVATION_APPROVED, RESERVATION_READY, RESERVATION_REJECTED

4. ADD APPOINTMENT REMINDER JOBS
   - Create scheduled task for APPOINTMENT_REMINDER_1 (1 day before)
   - Create scheduled task for APPOINTMENT_REMINDER_2 (3 hours before)
   - Notify receptionists for internal reminders

5. CONSIDER CLINIC_SERVICES & PATIENTS
   - Define if receptionists should receive notifications for service/patient changes
   - Add corresponding notification types if needed
""")
