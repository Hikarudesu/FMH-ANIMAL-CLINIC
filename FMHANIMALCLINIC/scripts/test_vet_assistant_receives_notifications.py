#!/usr/bin/env python
"""
Comprehensive test to verify Vet Assistant receives all relevant notifications
and doesn't receive irrelevant ones.
"""

import os
import sys
import django

# Setup Django
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'FMHANIMALCLINIC.settings')
django.setup()

from django.contrib.auth import get_user_model
from accounts.rbac_models import Role, Module
from notifications.models import Notification
from notifications.views import get_allowed_notification_types_for_user, get_notification_type_to_module_mapping
from notifications.signals import *  # Import signals to ensure they're registered
from appointments.models import Appointment
from inventory.models import Product, StockAdjustment
from records.models import MedicalRecord, RecordEntry
from patients.models import Pet
from branches.models import Branch
from employees.models import StaffMember
from datetime import datetime, timedelta

User = get_user_model()


def print_section(title):
    """Print a formatted section header."""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def test_appointment_notification():
    """Test that Vet Assistant RECEIVES appointment notifications."""
    print_section("TEST 1: APPOINTMENT NOTIFICATIONS")
    
    try:
        vet_assistant = User.objects.filter(
            assigned_role__code='vet_assistant',
            is_active=True
        ).first()
        
        if not vet_assistant:
            print("⚠ No vet_assistant user found")
            return False
        
        branch = vet_assistant.branch if hasattr(vet_assistant, 'branch') else Branch.objects.first()
        if not branch:
            branch = Branch.objects.first()
        
        print(f"✓ Using user: {vet_assistant.username} in branch: {branch}")
        
        # Clear old test notifications
        Notification.objects.filter(
            user=vet_assistant,
            title__startswith="TEST_APPT:"
        ).delete()
        
        before_count = Notification.objects.filter(
            user=vet_assistant,
            module_context=Notification.ModuleContext.APPOINTMENTS
        ).count()
        
        # Create a test appointment (should trigger signal)
        appointment = Appointment.objects.create(
            pet_name="Test Pet - Appointment",
            appointment_date=datetime.now().date(),
            appointment_time=datetime.now().time(),
            branch=branch,
            status='PENDING',
        )
        
        after_count = Notification.objects.filter(
            user=vet_assistant,
            module_context=Notification.ModuleContext.APPOINTMENTS
        ).count()
        
        if after_count > before_count:
            print(f"  ✓ APPOINTMENT notification created and received")
            notification = Notification.objects.filter(
                user=vet_assistant,
                module_context=Notification.ModuleContext.APPOINTMENTS,
                notification_type=Notification.NotificationType.APPOINTMENT
            ).latest('created_at')
            print(f"    Type: {notification.notification_type}")
            print(f"    Title: {notification.title}")
            print(f"    In Filter: {notification.notification_type in [t[0] for t in get_allowed_notification_types_for_user(vet_assistant)]}")
            appointment.delete()
            return True
        else:
            print(f"  ✗ NO APPOINTMENT notification received")
            print(f"    Before: {before_count}, After: {after_count}")
            appointment.delete()
            return False
    except Exception as e:
        print(f"  ✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_inventory_notification():
    """Test that Vet Assistant RECEIVES inventory notifications."""
    print_section("TEST 2: INVENTORY NOTIFICATIONS")
    
    try:
        vet_assistant = User.objects.filter(
            assigned_role__code='vet_assistant',
            is_active=True
        ).first()
        
        if not vet_assistant:
            print("⚠ No vet_assistant user found")
            return False
        
        branch = vet_assistant.branch if hasattr(vet_assistant, 'branch') else Branch.objects.first()
        if not branch:
            branch = Branch.objects.first()
        
        print(f"✓ Using user: {vet_assistant.username}")
        
        # Test Low Inventory Notification
        print(f"\n  Creating product with low stock...")
        before_count = Notification.objects.filter(
            user=vet_assistant,
            module_context=Notification.ModuleContext.INVENTORY
        ).count()
        
        # Create a product with low stock (should trigger notification)
        product = Product.objects.create(
            name="Test Product - Low Stock",
            sku="TEST-LOW-" + str(datetime.now().timestamp()),
            stock_quantity=3,  # Below default threshold
            branch=branch,
        )
        
        after_count = Notification.objects.filter(
            user=vet_assistant,
            module_context=Notification.ModuleContext.INVENTORY
        ).count()
        
        result = False
        if after_count > before_count:
            print(f"  ✓ LOW_INVENTORY notification created")
            notification = Notification.objects.filter(
                user=vet_assistant,
                module_context=Notification.ModuleContext.INVENTORY
            ).latest('created_at')
            print(f"    Type: {notification.notification_type}")
            print(f"    In Filter: {notification.notification_type in [t[0] for t in get_allowed_notification_types_for_user(vet_assistant)]}")
            result = True
        else:
            print(f"  ⚠ No low inventory notification (may not have triggered)")
        
        product.delete()
        return result
    except Exception as e:
        print(f"  ✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_medical_record_notification():
    """Test that Vet Assistant RECEIVES medical record notifications."""
    print_section("TEST 3: MEDICAL RECORD NOTIFICATIONS")
    
    try:
        vet_assistant = User.objects.filter(
            assigned_role__code='vet_assistant',
            is_active=True
        ).first()
        
        if not vet_assistant:
            print("⚠ No vet_assistant user found")
            return False
        
        branch = vet_assistant.branch if hasattr(vet_assistant, 'branch') else Branch.objects.first()
        if not branch:
            branch = Branch.objects.first()
        
        print(f"✓ Using user: {vet_assistant.username}")
        
        before_count = Notification.objects.filter(
            user=vet_assistant,
            module_context=Notification.ModuleContext.MEDICAL_RECORDS
        ).count()
        
        # Create test pet and medical record
        pet = Pet.objects.create(
            name="Test Pet - Medical",
            species="Dog",
            breed="Labrador",
            branch=branch,
        )
        
        record = MedicalRecord.objects.create(
            pet=pet,
            created_by=vet_assistant,
        )
        
        # Create a record entry (if the status field exists)
        try:
            entry = RecordEntry.objects.create(
                record=record,
                date_recorded=datetime.now().date(),
            )
        except:
            # Model might have different fields
            pass
        
        after_count = Notification.objects.filter(
            user=vet_assistant,
            module_context=Notification.ModuleContext.MEDICAL_RECORDS
        ).count()
        
        if after_count > before_count:
            print(f"  ✓ MEDICAL_RECORD notification created")
            notification = Notification.objects.filter(
                user=vet_assistant,
                module_context=Notification.ModuleContext.MEDICAL_RECORDS
            ).latest('created_at')
            print(f"    Type: {notification.notification_type}")
            print(f"    In Filter: {notification.notification_type in [t[0] for t in get_allowed_notification_types_for_user(vet_assistant)]}")
            record.delete()
            pet.delete()
            return True
        else:
            print(f"  ⚠ No medical record notification (may not have triggered)")
            record.delete()
            pet.delete()
            return False
    except Exception as e:
        print(f"  ✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_filter_accuracy():
    """Verify that the filter matches exactly what the vet assistant can access."""
    print_section("TEST 4: FILTER ACCURACY")
    
    try:
        vet_assistant = User.objects.filter(
            assigned_role__code='vet_assistant',
            is_active=True
        ).first()
        
        if not vet_assistant:
            print("⚠ No vet_assistant user found")
            return False
        
        # Get allowed types
        allowed_types = set(t[0] for t in get_allowed_notification_types_for_user(vet_assistant))
        
        # Get accessible modules
        accessible_modules = set(
            vet_assistant.assigned_role.module_permissions.values_list('module__code', flat=True)
        )
        accessible_modules.update(['notifications', 'general'])
        
        # Map and verify
        type_to_module = get_notification_type_to_module_mapping()
        expected_types = set()
        
        for notif_type, module_context in type_to_module.items():
            # Include if accessible OR if it's general or notifications
            if module_context in accessible_modules or module_context == 'general' or module_context == 'notifications':
                # Skip superadmin-only and reserved modules
                if not module_context.startswith('_'):
                    expected_types.add(notif_type)
        
        print(f"  Allowed types: {len(allowed_types)}")
        print(f"  Expected types: {len(expected_types)}")
        
        if allowed_types == expected_types:
            print(f"  ✓ Filter is ACCURATE - matches accessible modules")
            return True
        else:
            missing = expected_types - allowed_types
            extra = allowed_types - expected_types
            if missing:
                print(f"  ✗ Missing types: {missing}")
            if extra:
                print(f"  ✗ Extra types: {extra}")
            return False
    except Exception as e:
        print(f"  ✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests."""
    print("\n" + "=" * 70)
    print("  VET ASSISTANT NOTIFICATION RECEPTION TEST")
    print("=" * 70)
    
    results = {
        "Appointments": test_appointment_notification(),
        "Inventory": test_inventory_notification(),
        "Medical Records": test_medical_record_notification(),
        "Filter Accuracy": test_filter_accuracy(),
    }
    
    print_section("TEST SUMMARY")
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for name, result in results.items():
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"  {name}: {status}")
    
    print(f"\n  Total: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n✓ ALL TESTS PASSED - Vet Assistant receives correct notifications!")
    else:
        print(f"\n⚠ {total - passed} test(s) failed - Check the output above")
    
    print("=" * 70 + "\n")


if __name__ == '__main__':
    main()
