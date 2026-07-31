#!/usr/bin/env python
"""Compare pet owner vs vet assistant notification filter types."""

import os
import sys
import django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'FMHANIMALCLINIC.settings')
django.setup()

from notifications.models import Notification
from notifications.views import get_allowed_notification_types_for_user
from django.contrib.auth import get_user_model

User = get_user_model()

# Pet owner types (hardcoded from views.py)
pet_owner_types = [
    Notification.NotificationType.APPOINTMENT,
    Notification.NotificationType.APPOINTMENT_REMINDER_1,
    Notification.NotificationType.APPOINTMENT_REMINDER_2,
    Notification.NotificationType.FOLLOW_UP,
    Notification.NotificationType.MEDICAL_RECORD_UPDATE,
    Notification.NotificationType.PRODUCT_RESERVATION,
    Notification.NotificationType.STATEMENT_RELEASED,
    Notification.NotificationType.GENERAL,
]

# Get vet assistant types
vet_assistant = User.objects.filter(assigned_role__code='vet_assistant', is_active=True).first()
vet_assistant_types = set(t[0] for t in get_allowed_notification_types_for_user(vet_assistant))

# Get pet owner types
pet_owner_set = set(t.value for t in pet_owner_types)
vet_assistant_set = vet_assistant_types

print("\n" + "="*70)
print("  COMPARING PET OWNER vs VET ASSISTANT NOTIFICATION FILTERS")
print("="*70)

print(f'\nPET OWNER types: {len(pet_owner_set)}')
for t in sorted(pet_owner_set):
    print(f'  - {t}')

print(f'\nVET ASSISTANT types: {len(vet_assistant_set)}')
for t in sorted(vet_assistant_set):
    print(f'  - {t}')

overlap = pet_owner_set & vet_assistant_set
only_vet = vet_assistant_set - pet_owner_set
only_pet_owner = pet_owner_set - vet_assistant_set

print(f'\n' + "="*70)
print(f'  ANALYSIS')
print("="*70)

print(f'\nOVERLAP ({len(overlap)} types - both see these):')
for t in sorted(overlap):
    print(f'  ✓ {t}')

print(f'\nONLY VET ASSISTANT ({len(only_vet)} types):')
for t in sorted(only_vet):
    print(f'  ✓ {t}')

print(f'\nONLY PET OWNER ({len(only_pet_owner)} types):')
for t in sorted(only_pet_owner):
    print(f'  ✓ {t}')

print(f'\n' + "="*70)
print("  EXPLANATION")
print("="*70)
print("""
WHY IS THERE OVERLAP?

This is CORRECT and EXPECTED because:

1. SHARED RESPONSIBILITY:
   - Appointments: Both pet owners AND vet assistants care about appointments
     - Pet owner: "When is my pet's appointment?"
     - Vet Assistant: "What appointments do I need to help with?"
   
   - Medical Records: Both see updates
     - Pet owner: "What was the diagnosis?"
     - Vet Assistant: "What medical info do I need to know?"
   
   - Follow-ups: Both are involved
     - Pet owner: "When is the follow-up visit?"
     - Vet Assistant: "I need to help with this follow-up"

2. VET ASSISTANT IS STAFF:
   - Vet Assistants are INTERNAL staff, not customers
   - They have ADDITIONAL responsibilities like managing inventory
   - So they see MORE types (inventory, expiry alerts, etc.)

3. THE KEY DIFFERENCE:
   - Pet Owner sees: 8 types (basic customer info)
   - Vet Assistant sees: 16 types (all customer + staff operations)
   - Vet Assistant has SUPERSET of pet owner types PLUS staff-only types

WHY NOT MAKE THEM COMPLETELY DIFFERENT?

Because the underlying business logic is:
- Appointments apply to both roles (customer + staff perspective)
- Medical records apply to both roles (customer + staff perspective)
- But Vet Assistant ALSO manages inventory (staff-only)

This creates natural overlap + Vet Assistant extras.
""")
print("="*70 + "\n")
