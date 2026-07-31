#!/usr/bin/env python3
import os
import sys
from pathlib import Path

import django

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'FMHANIMALCLINIC.settings')
django.setup()

from accounts.models import User
from accounts.rbac_models import ModulePermission, Role
from notifications.models import Notification
from notifications.views import (
    get_allowed_notification_types_for_user,
    get_notification_type_to_module_mapping,
)


def normalize_module(value):
    if hasattr(value, 'value'):
        return value.value
    return value


def main():
    role = Role.objects.get(code='veterinarian')
    vet_user = User.objects.filter(assigned_role=role, is_active=True).first()

    role_modules = sorted(
        set(ModulePermission.objects.filter(role=role).values_list('module__code', flat=True))
    )
    accessible_modules = set(role_modules)
    accessible_modules.update({'notifications', 'general'})

    mapping = get_notification_type_to_module_mapping()
    allowed_codes = []
    if vet_user:
        allowed_codes = [code for code, _ in get_allowed_notification_types_for_user(vet_user)]

    print('Veterinarian role:', role.name, f'({role.code})')
    print('Role modules:', ', '.join(role_modules) if role_modules else '(none)')
    print('Vet user:', vet_user.username if vet_user else '(none)')
    print()
    print('{:32} {:24} {:14} {:14}'.format('Notification Type', 'Mapped Module', 'Role Module', 'In Filter'))
    print('-' * 88)

    mismatches = []
    for code, _label in Notification.NotificationType.choices:
        mapped_module = normalize_module(mapping.get(code, Notification.ModuleContext.GENERAL))
        role_has_module = mapped_module in accessible_modules or mapped_module == Notification.ModuleContext.GENERAL.value
        in_filter = code in allowed_codes
        print('{:32} {:24} {:14} {:14}'.format(code, str(mapped_module), str(role_has_module), str(in_filter)))
        if role_has_module != in_filter:
            mismatches.append((code, mapped_module, role_has_module, in_filter))

    print()
    print('Allowed filter types:', ', '.join(allowed_codes) if allowed_codes else '(none)')
    print('Mismatches:', mismatches if mismatches else 'none')


if __name__ == '__main__':
    main()
