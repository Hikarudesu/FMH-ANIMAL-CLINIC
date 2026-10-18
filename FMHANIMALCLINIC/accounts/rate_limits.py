"""Shared PostgreSQL-backed request throttles for security-sensitive flows."""

from datetime import timedelta
from math import ceil

from django.db import transaction
from django.db.models import F
from django.utils import timezone
from django.utils.crypto import salted_hmac

from .rate_limit_models import SharedRateLimitBucket


BUCKET_RETENTION = timedelta(days=2)
_last_cleanup_at = None


def _key_hash(scope, identity):
    return salted_hmac('accounts.shared-rate-limit', f'{scope}:{identity}').hexdigest()


def consume_rate_limit(scope, identity, limit, window_seconds):
    """Consume one quota slot; return retry seconds, or zero when allowed."""
    global _last_cleanup_at

    now = timezone.now()
    window_start = (
        now - timedelta(seconds=int(now.timestamp()) % window_seconds)
    ).replace(microsecond=0)
    key_hash = _key_hash(scope, identity)

    with transaction.atomic():
        bucket, _created = SharedRateLimitBucket.objects.get_or_create(
            key_hash=key_hash,
            window_start=window_start,
        )
        consumed = SharedRateLimitBucket.objects.filter(
            pk=bucket.pk,
            request_count__lt=limit,
        ).update(request_count=F('request_count') + 1)

        if _last_cleanup_at is None or now - _last_cleanup_at >= timedelta(hours=1):
            SharedRateLimitBucket.objects.filter(
                window_start__lt=now - BUCKET_RETENTION,
            ).delete()
            _last_cleanup_at = now

    if consumed:
        return 0
    remaining = (window_start + timedelta(seconds=window_seconds) - now).total_seconds()
    return max(1, ceil(remaining))


def clear_rate_limit(scope, identity):
    """Clear a bucket after successful authentication or OTP verification."""
    SharedRateLimitBucket.objects.filter(key_hash=_key_hash(scope, identity)).delete()