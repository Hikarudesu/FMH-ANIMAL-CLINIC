#!/usr/bin/env python
"""Check current receptionist permissions."""
import os
import sys
import django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'FMHANIMALCLINIC.settings')
django.setup()

from accounts.rbac_models import Role, ModulePermission

receptionist = Role.objects.get(code='receptionist')
perms = ModulePermission.objects.filter(role=receptionist).order_by('module__code', 'permission_type')

print('Current Receptionist Permissions:')
for perm in perms:
    print(f'  {perm.module.code}: {perm.permission_type}')

print(f'\nTotal: {perms.count()}')

# Check for problem modules
inq = ModulePermission.objects.filter(role=receptionist, module__code='inquiries')
res = ModulePermission.objects.filter(role=receptionist, module__code='reservations')
inv = ModulePermission.objects.filter(role=receptionist, module__code='inventory')

print(f'\n--- ISSUES ---')
print(f'Inquiries: {inq.count()} permissions (should be 0)')
if inq.count() > 0:
    print('  ' + str(list(inq.values_list('permission_type', flat=True))))

print(f'Reservations: {res.count()} permissions (should be 0)')
if res.count() > 0:
    print('  ' + str(list(res.values_list('permission_type', flat=True))))

print(f'Inventory: {list(inv.values_list("permission_type", flat=True))} (should be ["VIEW"] only)')
if set(inv.values_list('permission_type', flat=True)) != {'VIEW'}:
    print('  ERROR: Inventory has wrong permissions!')
