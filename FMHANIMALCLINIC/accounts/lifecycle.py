"""Account lifecycle operations that preserve owner records."""

from dateutil.relativedelta import relativedelta
from django.db.models import Q
from django.utils import timezone


def schedule_owner_deactivation(user, now=None):
    now = now or timezone.now()
    user.owner_deactivation_requested_at = now
    user.owner_deactivation_due_at = now + relativedelta(months=1)
    user.save(update_fields=[
        'owner_deactivation_requested_at',
        'owner_deactivation_due_at',
    ])


def resolve_owner_deactivation_on_login(user, now=None):
    """Cancel a pending request on timely login, or expire it if overdue."""
    now = now or timezone.now()
    due_at = user.owner_deactivation_due_at
    if not due_at or not user.is_pet_owner():
        return None

    if due_at <= now:
        user.is_active = False
        user.owner_account_deactivated_at = now
        user.save(update_fields=['is_active', 'owner_account_deactivated_at'])
        return 'expired'

    user.owner_deactivation_requested_at = None
    user.owner_deactivation_due_at = None
    user.save(update_fields=[
        'owner_deactivation_requested_at',
        'owner_deactivation_due_at',
    ])
    return 'cancelled'


def expire_due_owner_accounts(now=None):
    """Soft-deactivate pet-owner accounts whose grace period has elapsed."""
    from accounts.models import User

    now = now or timezone.now()
    owner_roles = Q(assigned_role__isnull=True) | Q(assigned_role__is_staff_role=False)
    return User.objects.filter(
        owner_roles,
        is_active=True,
        is_superuser=False,
        owner_deactivation_due_at__lte=now,
    ).update(
        is_active=False,
        owner_account_deactivated_at=now,
    )