#!/usr/bin/env python
"""Deep scan of receptionist role permissions."""
import os
import sys
import django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'FMHANIMALCLINIC.settings')
django.setup()

from accounts.rbac_models import Role, ModulePermission, Module

receptionist = Role.objects.get(code='receptionist')

# Get all module permissions for receptionist
all_perms = ModulePermission.objects.filter(role=receptionist).select_related('module')

print("="*80)
print("RECEPTIONIST ACTUAL PERMISSIONS IN DATABASE")
print("="*80)

# Group by module
modules_dict = {}
for perm in all_perms:
    module_code = perm.module.code
    if module_code not in modules_dict:
        modules_dict[module_code] = []
    modules_dict[module_code].append(perm.permission_type)

print(f"\nReceptionist has access to {len(modules_dict)} modules:\n")
for module_code in sorted(modules_dict.keys()):
    perms = modules_dict[module_code]
    print(f"{module_code}: {', '.join(sorted(perms))}")

print(f"\n\nTotal modules: {len(modules_dict)}")
print(f"Total permissions: {all_perms.count()}")

# List all modules in system
print("\n" + "="*80)
print("ALL MODULES AVAILABLE IN SYSTEM:")
print("="*80)
all_modules = list(Module.objects.all().order_by('code').values_list('code', flat=True))
for module_code in all_modules:
    has_it = "✓" if module_code in modules_dict else "✗"
    print(f"  {has_it} {module_code}")

print(f"\nTotal modules in system: {len(all_modules)}")
