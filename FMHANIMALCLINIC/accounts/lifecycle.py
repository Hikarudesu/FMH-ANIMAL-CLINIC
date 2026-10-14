"""Account lifecycle operations that preserve owner records."""

import logging
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.db.models import Q
from django.utils import timezone

logger = logging.getLogger('fmh')


def _send_owner_deactivation_email(user, *, completed):
    recipient = (user.email or '').strip()
    if not recipient:
        logger.warning('Cannot send account deactivation email for owner %s: no email address.', user.pk)
        return False

    name = user.get_full_name() or user.username
    if completed:
        subject = 'Your FMH Animal Clinic account has been deactivated'
        message = (
            f'Hello {name},\n\n'
            'Your pet-owner account has now been deactivated after its 30-day recovery period.\n\n'
            'Your records remain archived. If you create a new account and want to recover '
            'your records, please contact the clinic so an administrator can link them to your account.\n\n'
            'FMH Animal Clinic'
        )
    else:
        due_at = timezone.localtime(user.owner_deactivation_due_at)
        subject = 'Your FMH Animal Clinic account deactivation is scheduled'
        message = (
            f'Hello {name},\n\n'
            'You selected Deactivate account in My Profile. Your account is scheduled '
            f'to deactivate on {due_at:%B %d, %Y}, after a 30-day recovery period.\n\n'
            'You can cancel the scheduled deactivation by signing in before that date. '
            'Your records will be retained.\n\n'
            'FMH Animal Clinic'
        )

    try:
        sent_count = send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [recipient],
            fail_silently=False,
        )
    except Exception:
        logger.exception('Account deactivation email failed for owner %s.', user.pk)
        return False
    return sent_count == 1


def _deactivate_due_owner_account(user, now):
    updated = type(user).objects.filter(
        pk=user.pk,
        is_active=True,
        owner_deactivation_due_at__lte=now,
    ).update(
        is_active=False,
        owner_account_deactivated_at=now,
    )
    if not updated:
        return False

    user.is_active = False
    user.owner_account_deactivated_at = now
    _send_owner_deactivation_email(user, completed=True)
    return True


def schedule_owner_deactivation(user, now=None):
    now = now or timezone.now()
    user.owner_deactivation_requested_at = now
    user.owner_deactivation_due_at = now + timedelta(days=30)
    user.save(update_fields=[
        'owner_deactivation_requested_at',
        'owner_deactivation_due_at',
    ])
    return _send_owner_deactivation_email(user, completed=False)


def resolve_owner_deactivation_on_login(user, now=None):
    """Cancel a scheduled deactivation on timely login, or expire it if overdue."""
    now = now or timezone.now()
    due_at = user.owner_deactivation_due_at
    if not due_at or not user.is_pet_owner():
        return None

    if due_at <= now:
        _deactivate_due_owner_account(user, now)
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
    due_users = User.objects.filter(
        owner_roles,
        is_active=True,
        is_superuser=False,
        owner_deactivation_due_at__lte=now,
    ).only('pk', 'email', 'username', 'first_name', 'last_name')

    deactivated_count = 0
    for user in due_users:
        deactivated_count += _deactivate_due_owner_account(user, now)
    return deactivated_count