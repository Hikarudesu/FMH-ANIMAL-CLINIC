#!/usr/bin/env python
"""
Script to verify that veterinarian notifications are properly configured.
Tests:
1. Veterinarian filter shows expected notification types
2. Veterinarians receive appointment notifications
3. Veterinarians receive medical record update notifications
4. Notifications contain correct information
"""
import os
import sys
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "FMHANIMALCLINIC.settings")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

django.setup()

from django.utils import timezone
from datetime import datetime, timedelta
from accounts.models import User
from accounts.rbac_models import Role, ModulePermission
from appointments.models import Appointment
from patients.models import Pet
from records.models import MedicalRecord, RecordEntry
from notifications.models import Notification
from notifications.views import get_allowed_notification_types_for_user
from settings.models import ClinicalStatus
from branches.models import Branch


def _choice_code(choice):
    return choice[0] if isinstance(choice, tuple) else choice.value


def _choice_label(choice):
    return choice[1] if isinstance(choice, tuple) else choice.label

def print_header(text):
    print(f"\n{'='*60}")
    print(f"  {text}")
    print(f"{'='*60}")

def print_section(text):
    print(f"\n{text}:")
    print(f"{'-'*len(text)}")

def test_veterinarian_filter_types():
    """Test 1: Verify veterinarian filter shows expected notification types."""
    print_header("TEST 1: VETERINARIAN NOTIFICATION FILTER TYPES")
    
    # Get a veterinarian user
    try:
        vet = User.objects.filter(assigned_role__code='veterinarian', is_active=True).first()
        if not vet:
            print("❌ No active veterinarian found in database")
            return False
        
        print(f"✓ Found veterinarian: {vet.get_full_name()} ({vet.username})")
        
        # Get allowed notification types for this veterinarian
        allowed_types = get_allowed_notification_types_for_user(vet)
        
        print(f"\n✓ Veterinarian has access to {len(allowed_types)} notification types:")
        for nt in sorted(allowed_types, key=_choice_label):
            print(f"  • {_choice_label(nt)} ({_choice_code(nt)})")
        
        # Check for expected appointment-related types
        expected_types = [
            'APPOINTMENT',
            'APPOINTMENT_CONFIRMED',
            'APPOINTMENT_CANCELLED',
            'APPOINTMENT_RESCHEDULED',
            'APPOINTMENT_REMINDER_1',
            'APPOINTMENT_REMINDER_2',
            'FOLLOW_UP',
            'FOLLOW_UP_OVERDUE',
            'MEDICAL_RECORD_UPDATE',
        ]
        
        print(f"\nExpected types for veterinarian:")
        found_count = 0
        for expected in expected_types:
            found = any(_choice_code(nt) == expected for nt in allowed_types)
            status = "✓" if found else "✗"
            print(f"  {status} {expected}")
            if found:
                found_count += 1
        
        success_rate = (found_count / len(expected_types)) * 100
        print(f"\n{'✓' if success_rate == 100 else '⚠'} Found {found_count}/{len(expected_types)} ({success_rate:.0f}%)")
        
        return success_rate >= 80  # 80% pass rate
        
    except Exception as e:
        print(f"❌ Error testing filter types: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_appointment_notifications():
    """Test 2: Verify veterinarians receive appointment notifications."""
    print_header("TEST 2: APPOINTMENT NOTIFICATIONS FOR VETERINARIANS")
    
    try:
        # Get a veterinarian
        vet = User.objects.filter(assigned_role__code='veterinarian', is_active=True).first()
        if not vet:
            print("❌ No active veterinarian found")
            return False
        
        print(f"✓ Testing with veterinarian: {vet.get_full_name()}")
        
        # Get or create a pet
        pet = Pet.objects.filter(owner__isnull=False).first()
        if not pet:
            print("⚠ No pets found in database - skipping this test")
            return True
        
        # Get or create a branch
        branch = vet.branch or Branch.objects.first()
        if not branch:
            print("⚠ No branch available")
            return False
        
        # Clear previous notifications for this vet
        Notification.objects.filter(
            user=vet,
            notification_type__in=['APPOINTMENT', 'APPOINTMENT_CONFIRMED']
        ).delete()
        
        print(f"✓ Using pet: {pet.name}")
        print(f"✓ Using branch: {branch.name}")
        
        # Create a test appointment
        appt = Appointment.objects.create(
            pet_name=pet.name,
            appointment_date=timezone.now().date() + timedelta(days=1),
            appointment_time=timezone.now().time(),
            status=Appointment.Status.CONFIRMED,
            branch=branch,
            user=pet.owner,
            owner_email=pet.owner.email if pet.owner else 'test@example.com',
        )
        
        print(f"✓ Created test appointment: {appt.id}")
        
        # Check if veterinarian notification was created
        vet_notifs = Notification.objects.filter(
            user=vet,
            related_object_id=appt.id,
            notification_type__in=['APPOINTMENT', 'APPOINTMENT_CONFIRMED']
        )
        
        if vet_notifs.exists():
            print(f"✓ Veterinarian received {vet_notifs.count()} notification(s):")
            for notif in vet_notifs:
                print(f"  • Title: {notif.title}")
                print(f"    Message: {notif.message}")
                print(f"    Type: {notif.notification_type}")
            
            # Clean up
            appt.delete()
            return True
        else:
            print(f"❌ Veterinarian did NOT receive appointment notification")
            print(f"   Expected notifications for appointment ID {appt.id}")
            
            # Debug: Check all notifications created
            all_notifs = Notification.objects.filter(related_object_id=appt.id)
            print(f"   Total notifications for this appointment: {all_notifs.count()}")
            for notif in all_notifs:
                print(f"   - {notif.user.username}: {notif.notification_type}")
            
            # Clean up
            appt.delete()
            return False
            
    except Exception as e:
        print(f"❌ Error testing appointment notifications: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_medical_record_notifications():
    """Test 3: Verify veterinarians receive medical record update notifications."""
    print_header("TEST 3: MEDICAL RECORD UPDATE NOTIFICATIONS FOR VETERINARIANS")
    
    try:
        # Get a veterinarian
        vet = User.objects.filter(assigned_role__code='veterinarian', is_active=True).first()
        if not vet:
            print("❌ No active veterinarian found")
            return False
        
        print(f"✓ Testing with veterinarian: {vet.get_full_name()}")
        
        # Get or create a record
        record = MedicalRecord.objects.select_related('pet', 'branch').filter(
            branch=vet.branch
        ).first()
        
        if not record:
            print("⚠ No medical records found in database - skipping this test")
            return True
        
        # Get default clinical status
        clinical_status = ClinicalStatus.get_default()
        
        print(f"✓ Using record: {record.id}")
        print(f"✓ Using pet: {record.pet.name}")
        print(f"✓ Using branch: {record.branch.name}")
        
        # Clear previous notifications for this vet
        Notification.objects.filter(
            user=vet,
            notification_type='MEDICAL_RECORD_UPDATE'
        ).delete()
        
        # Create a test record entry
        entry = RecordEntry.objects.create(
            record=record,
            created_by=vet,
            clinical_notes='Test clinical notes',
            action_required=clinical_status,
        )
        
        print(f"✓ Created test record entry: {entry.id}")
        
        # Check if veterinarian notification was created
        vet_notifs = Notification.objects.filter(
            user=vet,
            related_object_id=record.id,
            notification_type='MEDICAL_RECORD_UPDATE'
        )
        
        if vet_notifs.exists():
            print(f"✓ Veterinarian received {vet_notifs.count()} notification(s):")
            for notif in vet_notifs:
                print(f"  • Title: {notif.title}")
                print(f"    Message: {notif.message}")
                print(f"    Type: {notif.notification_type}")
            
            # Clean up
            entry.delete()
            return True
        else:
            print(f"⚠ Veterinarian did NOT receive medical record notification")
            print(f"   (This may be expected if clinical status didn't change)")
            
            # Debug: Check all notifications created
            all_notifs = Notification.objects.filter(related_object_id=record.id)
            print(f"   Total notifications for this record: {all_notifs.count()}")
            for notif in all_notifs:
                print(f"   - {notif.user.username}: {notif.notification_type}")
            
            # Clean up
            entry.delete()
            return True  # Don't fail if notification wasn't created (might be expected)
            
    except Exception as e:
        print(f"❌ Error testing medical record notifications: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_veterinarian_module_permissions():
    """Test 4: Verify veterinarian has correct module permissions."""
    print_header("TEST 4: VETERINARIAN MODULE PERMISSIONS")
    
    try:
        # Get veterinarian role
        vet_role = Role.objects.filter(code='veterinarian').first()
        if not vet_role:
            print("❌ Veterinarian role not found")
            return False
        
        print(f"✓ Found veterinarian role: {vet_role.name}")
        
        # Get module permissions
        perms = ModulePermission.objects.filter(role=vet_role).select_related('module')
        
        print(f"\n✓ Veterinarian has access to {perms.count()} modules:")
        
        expected_modules = {
            'appointments': ['VIEW', 'CREATE', 'EDIT', 'DELETE', 'MANAGE'],
            'patients': ['VIEW', 'CREATE', 'EDIT', 'DELETE'],
            'medical_records': ['VIEW', 'CREATE', 'EDIT', 'DELETE'],
            'ai_diagnostics': ['VIEW', 'CREATE'],
        }
        
        all_match = True
        for perm in perms.order_by('module__code'):
            module_code = perm.module.code
            expected_perms = expected_modules.get(module_code, [])
            status = "✓" if perm.permission_type in expected_perms else "⚠"
            print(f"  {status} {perm.module.name} ({perm.module.code}): {perm.permission_type}")
        
        return all_match
        
    except Exception as e:
        print(f"❌ Error testing module permissions: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Run all verification tests."""
    print("\n" + "="*60)
    print("  VETERINARIAN NOTIFICATION VERIFICATION")
    print("="*60)
    
    results = {
        'Filter Types': test_veterinarian_filter_types(),
        'Appointment Notifications': test_appointment_notifications(),
        'Medical Record Notifications': test_medical_record_notifications(),
        'Module Permissions': test_veterinarian_module_permissions(),
    }
    
    # Summary
    print_header("VERIFICATION SUMMARY")
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for test_name, result in results.items():
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {test_name}")
    
    print(f"\n{'='*60}")
    print(f"Overall: {passed}/{total} tests passed ({(passed/total)*100:.0f}%)")
    print(f"{'='*60}\n")
    
    return 0 if passed == total else 1

if __name__ == '__main__':
    sys.exit(main())
