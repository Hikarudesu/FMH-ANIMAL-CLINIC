"""
Constants for RBAC role codes used throughout the application.
Centralizes role code strings to prevent typos and ensure consistency.
"""

# Staff role codes that can be scheduled
class StaffRoles:
    """Role codes for staff members who can be scheduled."""
    VETERINARIAN = 'veterinarian'
    VET_ASSISTANT = 'vet_assistant'
    RECEPTIONIST = 'receptionist'

    # Groupings for common queries
    SCHEDULABLE_ROLES = [VETERINARIAN, VET_ASSISTANT]
    ALL_STAFF_ROLES = [VETERINARIAN, VET_ASSISTANT, RECEPTIONIST]

# Admin role codes
class AdminRoles:
    """Role codes for administrative users."""
    SUPERADMIN = 'superadmin'
    BRANCH_ADMIN = 'branch_admin'

    ALL_ADMIN_ROLES = [SUPERADMIN, BRANCH_ADMIN]
