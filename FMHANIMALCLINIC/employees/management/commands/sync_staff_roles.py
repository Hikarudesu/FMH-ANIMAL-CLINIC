"""Management command to sync StaffMember.position with User.assigned_role."""
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from employees.models import StaffMember


class Command(BaseCommand):
    """Sync StaffMember.position with User.assigned_role."""

    help = 'Sync all StaffMember positions to match their User assigned_role'

    # Mapping from RBAC role code to StaffMember.Position value
    ROLE_MAPPING = {
        'veterinarian': StaffMember.Position.VETERINARIAN,
        'vet_assistant': StaffMember.Position.VET_ASSISTANT,
        'receptionist': StaffMember.Position.RECEPTIONIST,
        'admin': StaffMember.Position.ADMIN,
        'branch_admin': StaffMember.Position.ADMIN,
        'superadmin': StaffMember.Position.ADMIN,
    }

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be changed without making changes',
        )
        parser.add_argument(
            '--staff-id',
            type=int,
            help='Sync a specific staff member by ID',
        )

    def handle(self, *args, **options):
        dry_run = options.get('dry_run', False)
        staff_id = options.get('staff_id')

        # Build query
        query = StaffMember.objects.select_related('user', 'user__assigned_role').filter(
            user__isnull=False,
            user__assigned_role__isnull=False,
        )

        if staff_id:
            query = query.filter(pk=staff_id)

        # Find mismatches
        mismatches = []
        for staff in query:
            role_code = staff.user.assigned_role.code
            expected_position = self.ROLE_MAPPING.get(role_code)

            if expected_position and staff.position != expected_position:
                mismatches.append({
                    'staff': staff,
                    'current_position': staff.position,
                    'expected_position': expected_position,
                    'role_code': role_code,
                })

        if not mismatches:
            self.stdout.write(
                self.style.SUCCESS('✓ All staff positions are in sync!')
            )
            return

        # Display mismatches
        self.stdout.write(
            self.style.WARNING(f'\n🔍 Found {len(mismatches)} mismatched position(s):\n')
        )

        for i, mismatch in enumerate(mismatches, 1):
            staff = mismatch['staff']
            self.stdout.write(
                f"{i}. {staff.full_name} (ID: {staff.id})\n"
                f"   Role: {mismatch['role_code']}\n"
                f"   Current Position: {mismatch['current_position']}\n"
                f"   Expected Position: {mismatch['expected_position']}\n"
            )

        if dry_run:
            self.stdout.write(
                self.style.NOTICE('\n[DRY RUN] Use without --dry-run to apply changes\n')
            )
            return

        # Apply changes
        updated_count = 0
        for mismatch in mismatches:
            staff = mismatch['staff']
            staff.position = mismatch['expected_position']
            staff.save(update_fields=['position'])
            updated_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f'\n✅ Successfully synced {updated_count} staff position(s)!'
            )
        )
