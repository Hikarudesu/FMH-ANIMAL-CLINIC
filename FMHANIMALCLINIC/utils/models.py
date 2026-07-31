"""
Shared core models and mixins to be used across apps.
"""

from django.db import models
from django.utils import timezone


class SoftDeleteManager(models.Manager):
    """
    Custom manager that only returns active (non-deleted) objects by default.
    Provides methods to access deleted items if needed.
    """

    def get_queryset(self):
        """By default, only return objects that are not marked as deleted."""
        return super().get_queryset().filter(is_deleted=False)

    def all_with_deleted(self):
        """Returns all objects, including deleted ones (e.g., for reporting histories)."""
        return super().get_queryset()

    def deleted_only(self):
        """Returns only the deleted objects."""
        return super().get_queryset().filter(is_deleted=True)


class SoftDeleteModel(models.Model):
    """
    Abstract base class providing soft deletion.
    Objects are marked as is_deleted=True rather than being removed from the database,
    preventing historic FK links (like Invoices or History) from breaking.
    """
    is_deleted = models.BooleanField(
        default=False,
        help_text="Designates whether this record should be treated as deleted."
    )
    deleted_at = models.DateTimeField(null=True, blank=True)

    # Use the custom manager as the default
    objects = SoftDeleteManager()

    # Keep a reference to the default manager just in case we need unfiltered access easily
    all_objects = models.Manager()

    class Meta:
        abstract = True

    def delete(self, using=None, keep_parents=False):  # pylint: disable=unused-argument
        """
        Soft delete the object: set is_deleted to True and log the deletion time.
        """
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.save(update_fields=['is_deleted', 'deleted_at'])

    def restore(self):
        """
        Restore a soft-deleted object.
        """
        self.is_deleted = False
        self.deleted_at = None
        self.save(update_fields=['is_deleted', 'deleted_at'])
