"""Database-backed rate limit buckets shared by all application instances."""

from django.db import models


class SharedRateLimitBucket(models.Model):
    """Store an anonymous hashed key and its counter for a fixed time window."""

    key_hash = models.CharField(max_length=64)
    window_start = models.DateTimeField()
    request_count = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['key_hash', 'window_start'],
                name='unique_shared_rate_limit_bucket',
            ),
        ]
        indexes = [
            models.Index(fields=['window_start']),
        ]