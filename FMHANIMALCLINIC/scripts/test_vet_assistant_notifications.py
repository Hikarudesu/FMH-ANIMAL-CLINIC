#!/usr/bin/env python
"""
Test script to verify Veterinarian Assistant role notification setup.
Tests that vet_assistant receives notifications for all their accessible modules.
"""

import os
import sys
import django

# Setup Django
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'FMHANIMALCLINIC.settings')
django.setup()

from django.contrib.auth import get_user_model
from accounts.rbac_models import Role, Module, ModulePermission
from notifications.models import Notification
from appointments.models import Appointment
from inventory.models import Product, StockAdjustment
from records.models import RecordEntry, MedicalRecord
from patients.models import Pet
from branches.models import Branch
from employees.models import StaffMember, Position
from datetime import datetime, timedelta

User = get_user_model()


def print_section(title):
    """Print a formatted section header."""
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print(f"{'=' * 70}\n")


def check_vet_assistant_role():
    """Check if vet_assistant role exists and has proper configuration."""
    print_section("1. VET_ASSISTANT ROLE CONFIGURATION")
    
    try:
        role = Role.objects.get(code='vet_assistant')
        print(f"✓ Role exists: {role.name}")
        print(f"  - Code: {role.code}")
        print(f"  - Hierarchy Level: {role.hierarchy_level}")
        print(f"  - Is System Role: {role.is_system_role}")
        print(f"  - Is Staff Role: {role.is_staff_role}")
        
        # Check module permissions
        modules = role.module_permissions.all()
        print(f"\n  Module Permissions ({modules.count()}):")
        for mp in modules:
            print(f"    - {mp.module.display_name}: {mp.permission_type} (Branch Restricted: {mp.restrict_to_branch})")
        
        return role
    except Role.DoesNotExist:
        print("✗ Role 'vet_assistant' does not exist!")
        return None


def check_module_notification_scoping():
    """Verify that Notification.scoped_for_user() works correctly for vet_assistant."""
    print_section("2. NOTIFICATION FILTERING BY MODULE RBAC")
    
    # Get/Create a test vet_assistant user
    try:
        vet_assistant_user = User.objects.filter(
            assigned_role__code='vet_assistant',
            is_active=True
        ).first()
        
        if not vet_assistant_user:
            print("✗ No active vet_assistant users found for testing")
            return
        
        print(f"✓ Found test user: {vet_assistant_user.username}")
        
        # Get accessible modules
        accessible_modules = vet_assistant_user.get_accessible_modules()
        module_codes = set(accessible_modules.values_list('code', flat=True))
        
        print(f"\n  Accessible Module Codes: {module_codes}")
        
        # Create test notifications for different modules
        test_cases = [
            (Notification.ModuleContext.APPOINTMENTS, True),
            (Notification.ModuleContext.PATIENTS, True),
            (Notification.ModuleContext.MEDICAL_RECORDS, True),
            (Notification.ModuleContext.INVENTORY, True),
            (Notification.ModuleContext.PAYROLL, False),  # Should NOT be visible
            (Notification.ModuleContext.SOA, False),  # Should NOT be visible
        ]
        
        print(f"\n  Module Context Visibility Test:")
        for module_context, should_be_visible in test_cases:
            # Create notification
            notif = Notification.objects.create(
                user=vet_assistant_user,
                title=f"Test: {module_context}",
                message=f"Test notification for {module_context}",
                notification_type=Notification.NotificationType.GENERAL,
                module_context=module_context,
            )
            
            # Check if it's in scoped results
            scoped_qs = Notification.scoped_for_user(vet_assistant_user)
            is_visible = scoped_qs.filter(id=notif.id).exists()
            
            status = "✓" if is_visible == should_be_visible else "✗"
            visibility = "VISIBLE" if is_visible else "HIDDEN"
            expected = "visible" if should_be_visible else "hidden"
            
            print(f"    {status} {module_context}: {visibility} (expected: {expected})")
            
            # Cleanup
            notif.delete()
        
    except Exception as e:
        print(f"✗ Error during module scoping test: {e}")


def check_notification_triggers():
    """Test that notifications are created for key events."""
    print_section("3. NOTIFICATION TRIGGER TESTS")
    
    try:
        # Get test branch and vet_assistant
        branch = Branch.objects.first()
        vet_assistant_user = User.objects.filter(
            assigned_role__code='vet_assistant',
            is_active=True,
            branch=branch,
        ).first()
        
        if not vet_assistant_user:
            print(f"✗ No vet_assistant user found in branch {branch}")
            return
        
        print(f"✓ Using test user: {vet_assistant_user.username} in branch {branch}")
        
        # Clear old test notifications
        Notification.objects.filter(
            user=vet_assistant_user,
            title__startswith="TEST:"
        ).delete()
        
        # Test 1: New Appointment Notification
        print(f"\n  Test 1: New Appointment Notification")
        try:
            initial_count = Notification.objects.filter(
                user=vet_assistant_user,
                module_context=Notification.ModuleContext.APPOINTMENTS
            ).count()
            
            # Create new appointment (this should trigger signal)
            appointment = Appointment.objects.create(
                pet_name="Test Pet",
                appointment_date=datetime.now().date(),
                appointment_time=datetime.now().time(),
                branch=branch,
                status='PENDING',
            )
            
            after_count = Notification.objects.filter(
                user=vet_assistant_user,
                module_context=Notification.ModuleContext.APPOINTMENTS
            ).count()
            
            if after_count > initial_count:
                print(f"    ✓ Appointment notification created")
                appointment.delete()
            else:
                print(f"    ✗ No appointment notification created")
                appointment.delete()
        except Exception as e:
            print(f"    ✗ Error creating appointment: {e}")
        
        # Test 2: Low Inventory Notification
        print(f"\n  Test 2: Low Inventory Notification")
        try:
            initial_count = Notification.objects.filter(
                user=vet_assistant_user,
                module_context=Notification.ModuleContext.INVENTORY
            ).count()
            
            # Create product with low stock
            product = Product.objects.create(
                name="Test Product - Low Stock",
                sku="TEST-LOW",
                stock_quantity=5,  # Below default threshold of 10
                branch=branch,
            )
            
            after_count = Notification.objects.filter(
                user=vet_assistant_user,
                module_context=Notification.ModuleContext.INVENTORY
            ).count()
            
            if after_count > initial_count:
                print(f"    ✓ Low inventory notification created")
                product.delete()
            else:
                print(f"    ✗ No low inventory notification created")
                product.delete()
        except Exception as e:
            print(f"    ✗ Error creating product: {e}")
        
        # Test 3: Inventory Restock Notification
        print(f"\n  Test 3: Inventory Restock Notification")
        try:
            initial_count = Notification.objects.filter(
                user=vet_assistant_user,
                module_context=Notification.ModuleContext.INVENTORY,
                notification_type=Notification.NotificationType.INVENTORY_RESTOCK
            ).count()
            
            # Create product and stock adjustment
            product = Product.objects.create(
                name="Test Product - Restock",
                sku="TEST-RESTOCK",
                stock_quantity=50,
                branch=branch,
            )
            
            adjustment = StockAdjustment.objects.create(
                product=product,
                adjustment_type='ADD',
                quantity=20,
                reason='Test Restock',
            )
            
            after_count = Notification.objects.filter(
                user=vet_assistant_user,
                module_context=Notification.ModuleContext.INVENTORY,
                notification_type=Notification.NotificationType.INVENTORY_RESTOCK
            ).count()
            
            if after_count > initial_count:
                print(f"    ✓ Restock notification created")
                adjustment.delete()
                product.delete()
            else:
                print(f"    ✗ No restock notification created")
                adjustment.delete()
                product.delete()
        except Exception as e:
            print(f"    ✗ Error creating stock adjustment: {e}")
        
        # Test 4: Medical Record Update Notification
        print(f"\n  Test 4: Medical Record Clinical Status Update Notification")
        try:
            initial_count = Notification.objects.filter(
                user=vet_assistant_user,
                module_context=Notification.ModuleContext.MEDICAL_RECORDS
            ).count()
            
            # Create a pet and medical record
            pet = Pet.objects.create(
                name="Test Pet - Medical",
                species="Dog",
                owner=None,  # No owner for this test
            )
            
            record = MedicalRecord.objects.create(
                pet=pet,
                branch=branch,
                date_recorded=datetime.now().date(),
            )
            
            # Create record entry (this triggers the signal)
            from settings.models import ClinicalStatus
            clinical_status = ClinicalStatus.objects.first()
            
            entry = RecordEntry.objects.create(
                record=record,
                date_recorded=datetime.now().date(),
                action_required=clinical_status,
            )
            
            after_count = Notification.objects.filter(
                user=vet_assistant_user,
                module_context=Notification.ModuleContext.MEDICAL_RECORDS
            ).count()
            
            if after_count > initial_count:
                print(f"    ✓ Medical record notification created")
            else:
                print(f"    ✗ No medical record notification created")
            
            # Cleanup
            entry.delete()
            record.delete()
            pet.delete()
        except Exception as e:
            print(f"    ✗ Error creating medical record: {e}")
    
    except Exception as e:
        print(f"✗ Error during notification trigger tests: {e}")


def check_notification_count():
    """Count active notifications for vet_assistant users."""
    print_section("4. ACTIVE VET_ASSISTANT NOTIFICATIONS")
    
    vet_assistants = User.objects.filter(
        is_active=True,
        assigned_role__code='vet_assistant'
    )
    
    print(f"Found {vet_assistants.count()} active vet_assistant users\n")
    
    for user in vet_assistants:
        scoped_notifs = Notification.scoped_for_user(user).filter(is_read=False)
        print(f"  {user.username} (Branch: {user.branch}):")
        print(f"    - Unread notifications: {scoped_notifs.count()}")
        
        by_module = scoped_notifs.values('module_context').distinct()
        for item in by_module:
            module = item['module_context']
            count = scoped_notifs.filter(module_context=module).count()
            print(f"      • {module}: {count}")


def main():
    """Run all tests."""
    print("\n" + "=" * 70)
    print("  VETERINARIAN ASSISTANT NOTIFICATION SYSTEM TEST")
    print("=" * 70)
    
    role = check_vet_assistant_role()
    if not role:
        print("\n✗ Cannot proceed: vet_assistant role not found")
        return
    
    check_module_notification_scoping()
    check_notification_triggers()
    check_notification_count()
    
    print("\n" + "=" * 70)
    print("  TEST COMPLETED")
    print("=" * 70 + "\n")


if __name__ == '__main__':
    main()
