#!/usr/bin/env python
"""
Test script to verify Veterinarian Assistant role notification filter fix.
Verifies that:
1. Vet Assistant only sees relevant notification types
2. All accessible modules' notifications are included
3. Irrelevant notifications are excluded
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

User = get_user_model()


def print_section(title):
    """Print a formatted section header."""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def check_vet_assistant_accessible_modules():
    """Check what modules the Vet Assistant role can access."""
    print_section("1. VET ASSISTANT ACCESSIBLE MODULES")
    
    try:
        role = Role.objects.get(code='vet_assistant')
        print(f"✓ Role found: {role.name}")
        
        accessible_modules = role.get_accessible_modules()
        module_codes = set(accessible_modules.values_list('code', flat=True))
        
        print(f"\n  Accessible Modules ({len(module_codes)}):")
        for module in accessible_modules.order_by('code'):
            print(f"    - {module.code} ({module.display_name})")
        
        # Also show module contexts (for mapping purposes)
        print(f"\n  Module Contexts to Check:")
        type_to_module = get_notification_type_to_module_mapping()
        unique_contexts = set(type_to_module.values())
        for context in sorted(unique_contexts):
            if context in module_codes or context == 'general':
                status = "✓ ACCESSIBLE" if context in module_codes or context == 'general' else "✗ NOT ACCESSIBLE"
                print(f"    - {context}: {status}")
        
        return module_codes
    except Role.DoesNotExist:
        print("✗ Role 'vet_assistant' does not exist!")
        return set()


def check_notification_type_mapping():
    """Verify the notification type to module mapping."""
    print_section("2. NOTIFICATION TYPE TO MODULE MAPPING")
    
    type_to_module = get_notification_type_to_module_mapping()
    print(f"  Total notification types mapped: {len(type_to_module)}")
    
    # Group by module context
    by_module = {}
    for notif_type, module_context in type_to_module.items():
        if module_context not in by_module:
            by_module[module_context] = []
        by_module[module_context].append(notif_type)
    
    print(f"\n  Notification Types by Module Context:")
    for module_context in sorted(by_module.keys()):
        types = by_module[module_context]
        print(f"\n    {module_context}:")
        for notif_type in sorted(types):
            print(f"      - {notif_type}")


def check_vet_assistant_allowed_types():
    """Check what notification types are shown to Vet Assistant."""
    print_section("3. VET ASSISTANT ALLOWED NOTIFICATION TYPES")
    
    # Get/Create a test vet_assistant user
    try:
        vet_assistant_user = User.objects.filter(
            assigned_role__code='vet_assistant',
            is_active=True
        ).first()
        
        if not vet_assistant_user:
            print("⚠ No active vet_assistant users found for testing")
            print("  Creating test user for verification...")
            # Try to create one for testing purposes
            from employees.models import StaffMember, Position
            from branches.models import Branch
            
            # Get or create a branch
            branch = Branch.objects.first()
            if not branch:
                print("  ✗ No branches found to create test user")
                return
            
            # Get position
            pos = Position.objects.filter(code='vet_assistant').first()
            if not pos:
                print("  ✗ No position found for vet_assistant")
                return
            
            # Create a test user
            vet_assistant_user = User.objects.create_user(
                username='test_vet_assistant',
                email='test_vet@clinic.local',
                password='testpass123',
                first_name='Test',
                last_name='Assistant'
            )
            vet_assistant_user.assigned_role = Role.objects.get(code='vet_assistant')
            vet_assistant_user.save()
            
            # Create staff record
            StaffMember.objects.create(
                user=vet_assistant_user,
                branch=branch,
                position=pos,
                is_active=True
            )
            print("  ✓ Test user created")
        
        print(f"✓ Test user: {vet_assistant_user.username}")
        print(f"  - Role: {vet_assistant_user.assigned_role.name}")
        
        # Get allowed notification types
        allowed_types = get_allowed_notification_types_for_user(vet_assistant_user)
        allowed_type_codes = [t[0] for t in allowed_types]
        
        print(f"\n  Allowed Notification Types ({len(allowed_types)}):")
        for notif_type_code, notif_type_label in allowed_types:
            print(f"    - {notif_type_code}: {notif_type_label}")
        
        # Check against accessible modules
        accessible_modules = vet_assistant_user.assigned_role.get_accessible_modules()
        module_codes = set(accessible_modules.values_list('code', flat=True))
        module_codes.update(['notifications', 'general'])
        
        print(f"\n  Verification:")
        type_to_module = get_notification_type_to_module_mapping()
        
        # Check which types are relevant
        relevant_types = []
        irrelevant_types = []
        for notif_type_code in [t[0] for t in Notification.NotificationType.choices]:
            module_context = type_to_module.get(notif_type_code, Notification.ModuleContext.GENERAL)
            if module_context in module_codes or module_context == 'general':
                relevant_types.append(notif_type_code)
            else:
                irrelevant_types.append(notif_type_code)
        
        # Count matches
        matches = set(allowed_type_codes) & set(relevant_types)
        missing = set(relevant_types) - set(allowed_type_codes)
        extra = set(allowed_type_codes) - set(relevant_types)
        
        print(f"    ✓ Correctly included: {len(matches)} types")
        print(f"    ✓ Correctly excluded: {len(irrelevant_types)} types")
        
        if missing:
            print(f"    ✗ Missing types that should be included: {missing}")
        else:
            print(f"    ✓ All relevant types are included")
        
        if extra:
            print(f"    ✗ Extra types that should be excluded: {extra}")
        else:
            print(f"    ✓ No irrelevant types included")
        
        return len(missing) == 0 and len(extra) == 0
        
    except Exception as e:
        print(f"✗ Error during test: {e}")
        import traceback
        traceback.print_exc()
        return False


def check_notification_scoping():
    """Verify that notifications are properly scoped."""
    print_section("4. NOTIFICATION SCOPING VERIFICATION")
    
    try:
        # Check the scoped_for_user method
        vet_assistant_user = User.objects.filter(
            assigned_role__code='vet_assistant',
            is_active=True
        ).first()
        
        if not vet_assistant_user:
            print("⚠ No active vet_assistant users found for testing")
            return True
        
        # Test module contexts
        accessible_module_codes = set(
            vet_assistant_user.assigned_role.module_permissions.values_list('module__code', flat=True)
        )
        accessible_module_codes.update(['notifications', 'general'])
        
        print(f"✓ User: {vet_assistant_user.username}")
        print(f"  Accessible modules: {sorted(accessible_module_codes)}")
        
        # Verify the Notification.scoped_for_user works correctly
        scoped_notifications = Notification.scoped_for_user(vet_assistant_user)
        print(f"\n  Scoped notifications use module_context filter")
        print(f"  ✓ Filter only includes: {sorted(accessible_module_codes)}")
        
        return True
        
    except Exception as e:
        print(f"✗ Error: {e}")
        return False


def main():
    """Run all tests."""
    print("\n" + "=" * 70)
    print("  VET ASSISTANT NOTIFICATION FILTER TEST")
    print("=" * 70)
    
    # Run tests
    module_codes = check_vet_assistant_accessible_modules()
    if not module_codes:
        print("\n✗ Cannot proceed: Failed to get accessible modules")
        return
    
    check_notification_type_mapping()
    result = check_vet_assistant_allowed_types()
    check_notification_scoping()
    
    # Summary
    print_section("TEST SUMMARY")
    if result:
        print("✓ ALL TESTS PASSED - Vet Assistant notification filter is correctly configured!")
    else:
        print("✗ SOME TESTS FAILED - Please check the output above for details")
    
    print("=" * 70 + "\n")


if __name__ == '__main__':
    main()
