"""
Signal handlers for user and authentication events.
Logs user account creation and syncs profile data.

NOTE: Login/logout logging is handled by accounts/activity_signals.py
"""
from django.db.models.signals import post_save
from django.db.models.signals import post_delete, pre_save
from django.dispatch import receiver

from .models import User, ActivityLog
from utils.file_cleanup import safely_delete_field_file


@receiver(pre_save, sender=User)
def stash_old_profile_picture(sender, instance, **kwargs):
    """Keep track of old profile picture so we can delete it after a successful save."""
    instance._old_profile_picture = None  # pylint: disable=protected-access
    if not instance.pk:
        return

    try:
        old_instance = User.objects.only('profile_picture').get(pk=instance.pk)
    except User.DoesNotExist:
        return

    old_name = old_instance.profile_picture.name if old_instance.profile_picture else ''
    new_name = instance.profile_picture.name if instance.profile_picture else ''
    if old_name and old_name != new_name:
        instance._old_profile_picture = old_instance.profile_picture  # pylint: disable=protected-access


@receiver(post_save, sender=User)
def log_user_change(sender, instance, created, **kwargs):
    """Log when a user is created or updated."""
    if created:
        branch = None
        try:
            branch = instance.branch
        except Exception:
            branch = None

        if branch is not None:
            ActivityLog.objects.create(
                user=instance,
                action="User Account Created",
                category=ActivityLog.Category.USER,
                branch=branch,
                details=f"Username: {instance.username} | Role: {instance.get_display_role()}"
            )


@receiver(post_save, sender=User)
def sync_user_to_appointments(sender, instance, created, **kwargs):
    """
    When a User profile is updated, sync the changes to all related Appointments
    where the user is the pet owner. This ensures appointment owner contact info
    stays current when users update their profile.
    """
    # Skip for newly created users (no appointments yet)
    if created:
        return

    # Only sync for pet owners who might have appointments
    if not instance.is_pet_owner():
        return

    # Import here to avoid circular import
    from appointments.models import Appointment

    # Find all appointments for this user
    appointments = Appointment.objects.filter(user=instance)

    if not appointments.exists():
        return

    # Prepare owner info updates
    updates = {
        'owner_name': instance.get_full_name() or instance.username,
        'owner_phone': instance.phone_number or '',
        'owner_email': instance.email or '',
        'owner_address': instance.address or '',
    }

    # Bulk update all related appointments
    appointments.update(**updates)


@receiver(post_save, sender=User)
def sync_user_to_staff_profile(sender, instance, created, **kwargs):
    """
    When a User with staff role is updated, sync the changes to their StaffMember profile.
    Ensures branch, name, email, and phone stay synchronized between User and StaffMember.
    """
    # Skip for newly created users (handled by assign_user_role)
    if created:
        return

    # Only sync for staff users
    if not instance.is_clinic_staff():
        return

    # Import here to avoid circular import
    from django.core.exceptions import ObjectDoesNotExist
    # Get or skip if no staff profile exists
    try:
        staff_profile = instance.staff_profile
    except ObjectDoesNotExist:
        return

    # Sync key fields from User to StaffMember
    staff_profile.first_name = instance.first_name
    staff_profile.last_name = instance.last_name
    staff_profile.email = instance.email
    staff_profile.phone = instance.phone_number or ''
    staff_profile.branch = instance.branch

    staff_profile.save()


@receiver(post_save, sender=User)
def cleanup_replaced_profile_picture(sender, instance, **kwargs):
    """Delete replaced profile pictures only after new value was saved successfully."""
    old_file = getattr(instance, '_old_profile_picture', None)
    if old_file:
        safely_delete_field_file(old_file)


@receiver(post_delete, sender=User)
def cleanup_deleted_user_profile_picture(sender, instance, **kwargs):
    """Delete profile picture file when the user record is removed."""
    safely_delete_field_file(instance.profile_picture)
