"""Signals for comprehensive activity logging across the system."""

from django.db.models.signals import post_delete, post_save, pre_delete, pre_save
from django.dispatch import receiver
from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.contrib.auth import get_user_model
from accounts.models import ActivityLog, log_activity


def _resolve_actor(instance):
    """Return request actor when available; otherwise use a system fallback user."""
    actor = getattr(instance, '_user', None)
    if actor:
        return actor
    user_model = get_user_model()
    return user_model.objects.filter(is_superuser=True).first() or user_model.objects.first()

# ════════════════════════════════════════════════════════
# APPOINTMENT SIGNALS
# ════════════════════════════════════════════════════════

try:
    from appointments.models import Appointment

    @receiver(pre_save, sender=Appointment)
    def log_appointment_status_change(sender, instance, **kwargs):
        """Log appointment status transitions explicitly."""
        if not instance.pk:
            return

        try:
            old_status = Appointment.objects.only('status').get(pk=instance.pk).status
        except Appointment.DoesNotExist:
            return

        if old_status == instance.status:
            return

        user = _resolve_actor(instance)
        if not user:
            return

        ip_address = getattr(instance, '_ip_address', None)
        log_activity(
            user=user,
            action=f"Appointment status changed: {instance.pet_name}",
            category=ActivityLog.Category.APPOINTMENT,
            action_type=ActivityLog.ActionType.UPDATE,
            branch=instance.branch,
            details=f"Status changed from {old_status} to {instance.status}",
            object_type='Appointment',
            object_id=instance.id,
            ip_address=ip_address,
        )

    @receiver(post_save, sender=Appointment)
    def log_appointment_changes(sender, instance, created, **kwargs):
        """Log appointment creation and updates."""
        user = getattr(instance, '_user', None)
        if not user:
            return

        ip_address = getattr(instance, '_ip_address', None)

        if created:
            log_activity(
                user=user,
                action=f"Appointment created for {instance.pet_name}",
                category=ActivityLog.Category.APPOINTMENT,
                action_type=ActivityLog.ActionType.CREATE,
                branch=instance.branch,
                details=f"Pet: {instance.pet_name}, Owner: {instance.owner_name}",
                object_type='Appointment',
                object_id=instance.id,
                ip_address=ip_address
            )
        else:
            log_activity(
                user=user,
                action=f"Appointment updated: {instance.pet_name}",
                category=ActivityLog.Category.APPOINTMENT,
                action_type=ActivityLog.ActionType.UPDATE,
                branch=instance.branch,
                details=f"Status: {instance.status}",
                object_type='Appointment',
                object_id=instance.id,
                ip_address=ip_address
            )

    @receiver(pre_delete, sender=Appointment)
    def log_appointment_delete(sender, instance, **kwargs):
        """Log appointment deletions."""
        user = _resolve_actor(instance)
        if not user:
            return

        log_activity(
            user=user,
            action=f"Appointment deleted: {instance.pet_name}",
            category=ActivityLog.Category.APPOINTMENT,
            action_type=ActivityLog.ActionType.DELETE,
            branch=instance.branch,
            details=f"Owner: {instance.owner_name}",
            object_type='Appointment',
            object_id=instance.id,
            ip_address=getattr(instance, '_ip_address', None),
        )
except ImportError:
    pass

# ════════════════════════════════════════════════════════
# PET/PATIENT SIGNALS
# ════════════════════════════════════════════════════════

try:
    from patients.models import Pet

    @receiver(post_save, sender=Pet)
    def log_pet_changes(sender, instance, created, **kwargs):
        """Log pet creation and updates."""
        user = getattr(instance, '_user', None)
        if not user:
            return

        ip_address = getattr(instance, '_ip_address', None)

        if created:
            log_activity(
                user=user,
                action=f"Pet registered: {instance.name}",
                category=ActivityLog.Category.PATIENT,
                action_type=ActivityLog.ActionType.CREATE,
                details=f"Species: {instance.species}, Breed: {instance.breed}",
                object_type='Pet',
                object_id=instance.id,
                ip_address=ip_address
            )
        else:
            log_activity(
                user=user,
                action=f"Pet updated: {instance.name}",
                category=ActivityLog.Category.PATIENT,
                action_type=ActivityLog.ActionType.UPDATE,
                details=f"Status: {instance.status}",
                object_type='Pet',
                object_id=instance.id,
                ip_address=ip_address
            )

    @receiver(pre_delete, sender=Pet)
    def log_pet_delete(sender, instance, **kwargs):
        """Log pet deletions."""
        user = _resolve_actor(instance)
        if not user:
            return

        log_activity(
            user=user,
            action=f"Pet deleted: {instance.name}",
            category=ActivityLog.Category.PATIENT,
            action_type=ActivityLog.ActionType.DELETE,
            details=f"Species: {instance.species}",
            object_type='Pet',
            object_id=instance.id,
            ip_address=getattr(instance, '_ip_address', None),
        )
except ImportError:
    pass

# ════════════════════════════════════════════════════════
# MEDICAL RECORDS SIGNALS
# ════════════════════════════════════════════════════════

try:
    from records.models import MedicalRecord

    @receiver(post_save, sender=MedicalRecord)
    def log_medical_record_changes(sender, instance, created, **kwargs):
        """Log medical record creation and updates."""
        user = getattr(instance, '_user', None)
        if not user:
            return

        ip_address = getattr(instance, '_ip_address', None)

        if created:
            log_activity(
                user=user,
                action=f"Medical record created for {instance.pet.name}",
                category=ActivityLog.Category.MEDICAL,
                action_type=ActivityLog.ActionType.CREATE,
                details=f"Chief complaint: {instance.chief_complaint}",
                object_type='MedicalRecord',
                object_id=instance.id,
                ip_address=ip_address
            )
        else:
            log_activity(
                user=user,
                action=f"Medical record updated: {instance.pet.name}",
                category=ActivityLog.Category.MEDICAL,
                action_type=ActivityLog.ActionType.UPDATE,
                object_type='MedicalRecord',
                object_id=instance.id,
                ip_address=ip_address
            )

    @receiver(pre_delete, sender=MedicalRecord)
    def log_medical_record_delete(sender, instance, **kwargs):
        """Log medical record deletions."""
        user = _resolve_actor(instance)
        if not user:
            return

        log_activity(
            user=user,
            action=f"Medical record deleted for {instance.pet.name}",
            category=ActivityLog.Category.MEDICAL,
            action_type=ActivityLog.ActionType.DELETE,
            object_type='MedicalRecord',
            object_id=instance.id,
            ip_address=getattr(instance, '_ip_address', None),
        )
except ImportError:
    pass

# ════════════════════════════════════════════════════════
# POS/SALES SIGNALS
# ════════════════════════════════════════════════════════

try:
    from pos.models import Sale

    @receiver(post_save, sender=Sale)
    def log_sale_changes(sender, instance, created, **kwargs):
        """Log sale creation and updates."""
        user = getattr(instance, '_user', None)
        if not user:
            return

        ip_address = getattr(instance, '_ip_address', None)

        if created:
            log_activity(
                user=user,
                action=f"Sale created: {instance.transaction_id}",
                category=ActivityLog.Category.POS,
                action_type=ActivityLog.ActionType.CREATE,
                details=f"Amount: ₱{instance.total}, Customer: {instance.customer or instance.guest_name}",
                object_type='Sale',
                object_id=instance.id,
                ip_address=ip_address
            )
        else:
            log_activity(
                user=user,
                action=f"Sale updated: {instance.transaction_id}",
                category=ActivityLog.Category.POS,
                action_type=ActivityLog.ActionType.UPDATE,
                details=f"Status: {instance.status}",
                object_type='Sale',
                object_id=instance.id,
                ip_address=ip_address
            )
except ImportError:
    pass

# ════════════════════════════════════════════════════════
# BILLING SIGNALS
# ════════════════════════════════════════════════════════

try:
    from billing.models import CustomerStatement

    @receiver(post_save, sender=CustomerStatement)
    def log_statement_changes(sender, instance, created, **kwargs):
        """Log statement creation and updates."""
        user = getattr(instance, '_user', None)
        if not user:
            return

        ip_address = getattr(instance, '_ip_address', None)

        if created:
            log_activity(
                user=user,
                action=f"Statement created: {instance.id}",
                category=ActivityLog.Category.BILLING,
                action_type=ActivityLog.ActionType.CREATE,
                details=f"Amount: ₱{instance.total_amount}, Status: {instance.status}",
                object_type='CustomerStatement',
                object_id=instance.id,
                ip_address=ip_address
            )
        else:
            log_activity(
                user=user,
                action=f"Statement updated: {instance.id}",
                category=ActivityLog.Category.BILLING,
                action_type=ActivityLog.ActionType.UPDATE,
                details=f"Status: {instance.status}",
                object_type='CustomerStatement',
                object_id=instance.id,
                ip_address=ip_address
            )
except ImportError:
    pass

# ════════════════════════════════════════════════════════
# INVENTORY SIGNALS
# ════════════════════════════════════════════════════════

try:
    from inventory.models import Product

    @receiver(post_save, sender=Product)
    def log_product_changes(sender, instance, created, **kwargs):
        """Log product creation and updates."""
        user = getattr(instance, '_user', None)
        if not user:
            return

        ip_address = getattr(instance, '_ip_address', None)

        if created:
            log_activity(
                user=user,
                action=f"Product created: {instance.name}",
                category=ActivityLog.Category.STOCK,
                action_type=ActivityLog.ActionType.CREATE,
                branch=instance.branch,
                details=f"SKU: {instance.sku}, Stock: {instance.stock_quantity}",
                object_type='Product',
                object_id=instance.id,
                ip_address=ip_address
            )
        else:
            log_activity(
                user=user,
                action=f"Product updated: {instance.name}",
                category=ActivityLog.Category.STOCK,
                action_type=ActivityLog.ActionType.UPDATE,
                branch=instance.branch,
                details=f"Stock: {instance.stock_quantity}",
                object_type='Product',
                object_id=instance.id,
                ip_address=ip_address
            )

    @receiver(pre_delete, sender=Product)
    def log_product_delete(sender, instance, **kwargs):
        """Log product deletions."""
        user = _resolve_actor(instance)
        if not user:
            return

        log_activity(
            user=user,
            action=f"Product deleted: {instance.name}",
            category=ActivityLog.Category.STOCK,
            action_type=ActivityLog.ActionType.DELETE,
            branch=instance.branch,
            details=f"SKU: {instance.sku}",
            object_type='Product',
            object_id=instance.id,
            ip_address=getattr(instance, '_ip_address', None),
        )
except ImportError:
    pass

# ════════════════════════════════════════════════════════
# STAFF SIGNALS
# ════════════════════════════════════════════════════════

try:
    from employees.models import StaffMember

    @receiver(post_save, sender=StaffMember)
    def log_staff_changes(sender, instance, created, **kwargs):
        """Log staff creation and updates."""
        user = getattr(instance, '_user', None)
        if not user:
            return

        ip_address = getattr(instance, '_ip_address', None)

        if created:
            log_activity(
                user=user,
                action=f"Staff member added: {instance.user.get_full_name()}",
                category=ActivityLog.Category.STAFF,
                action_type=ActivityLog.ActionType.CREATE,
                branch=instance.branch,
                details=f"Position: {instance.position}",
                object_type='StaffMember',
                object_id=instance.id,
                ip_address=ip_address
            )
        else:
            log_activity(
                user=user,
                action=f"Staff member updated: {instance.user.get_full_name()}",
                category=ActivityLog.Category.STAFF,
                action_type=ActivityLog.ActionType.UPDATE,
                branch=instance.branch,
                details=f"Active: {instance.is_active}",
                object_type='StaffMember',
                object_id=instance.id,
                ip_address=ip_address
            )

    @receiver(pre_delete, sender=StaffMember)
    def log_staff_delete(sender, instance, **kwargs):
        """Log staff profile deletions."""
        user = _resolve_actor(instance)
        if not user:
            return

        log_activity(
            user=user,
            action=f"Staff member removed: {instance.user.get_full_name()}",
            category=ActivityLog.Category.STAFF,
            action_type=ActivityLog.ActionType.DELETE,
            branch=instance.branch,
            object_type='StaffMember',
            object_id=instance.id,
            ip_address=getattr(instance, '_ip_address', None),
        )
except ImportError:
    pass

# ════════════════════════════════════════════════════════
# PAYROLL SIGNALS
# ════════════════════════════════════════════════════════

try:
    from payroll.models import Payroll

    @receiver(post_save, sender=Payroll)
    def log_payroll_changes(sender, instance, created, **kwargs):
        """Log payroll creation and updates."""
        user = getattr(instance, '_user', None)
        if not user:
            return

        ip_address = getattr(instance, '_ip_address', None)

        if created:
            log_activity(
                user=user,
                action=f"Payroll created for {instance.staff_member.user.get_full_name()}",
                category=ActivityLog.Category.PAYROLL,
                action_type=ActivityLog.ActionType.CREATE,
                details=f"Amount: ₱{instance.total_salary}",
                object_type='Payroll',
                object_id=instance.id,
                ip_address=ip_address
            )
        else:
            log_activity(
                user=user,
                action=f"Payroll updated: {instance.staff_member.user.get_full_name()}",
                category=ActivityLog.Category.PAYROLL,
                action_type=ActivityLog.ActionType.UPDATE,
                object_type='Payroll',
                object_id=instance.id,
                ip_address=ip_address
            )

    @receiver(pre_delete, sender=Payroll)
    def log_payroll_delete(sender, instance, **kwargs):
        """Log payroll deletions."""
        user = _resolve_actor(instance)
        if not user:
            return

        log_activity(
            user=user,
            action=f"Payroll deleted for {instance.staff_member.user.get_full_name()}",
            category=ActivityLog.Category.PAYROLL,
            action_type=ActivityLog.ActionType.DELETE,
            object_type='Payroll',
            object_id=instance.id,
            ip_address=getattr(instance, '_ip_address', None),
        )
except ImportError:
    pass


try:
    from notifications.models import Notification

    @receiver(post_save, sender=Notification)
    def log_notification_events(sender, instance, created, **kwargs):
        """Log high-signal notification lifecycle events for superadmin visibility."""
        user = _resolve_actor(instance) or instance.user
        if not user:
            return

        action_type = ActivityLog.ActionType.CREATE if created else ActivityLog.ActionType.UPDATE
        action_label = 'created' if created else 'updated'
        details = f"Type: {instance.notification_type} | Read: {instance.is_read}"
        log_activity(
            user=user,
            action=f"Notification {action_label}: {instance.title}",
            category=ActivityLog.Category.SYSTEM,
            action_type=action_type,
            branch=getattr(user, 'branch', None),
            details=details,
            object_type='Notification',
            object_id=instance.id,
        )

    @receiver(pre_delete, sender=Notification)
    def log_notification_delete(sender, instance, **kwargs):
        """Log notification deletions."""
        user = _resolve_actor(instance) or instance.user
        if not user:
            return

        log_activity(
            user=user,
            action=f"Notification deleted: {instance.title}",
            category=ActivityLog.Category.SYSTEM,
            action_type=ActivityLog.ActionType.DELETE,
            branch=getattr(user, 'branch', None),
            details=f"Type: {instance.notification_type}",
            object_type='Notification',
            object_id=instance.id,
        )
except ImportError:
    pass

# ════════════════════════════════════════════════════════
# LOGIN/LOGOUT SIGNALS
# ════════════════════════════════════════════════════════


@receiver(user_logged_in)
def log_user_login(sender, request, user, **kwargs):
    """Log when a user successfully logs in."""
    ip_address = request.META.get('REMOTE_ADDR', None)
    log_activity(
        user=user,
        action="User Logged In",
        category=ActivityLog.Category.USER,
        action_type=ActivityLog.ActionType.LOGIN,
        branch=user.branch,
        details=f"IP: {ip_address}",
        ip_address=ip_address
    )


@receiver(user_logged_out)
def log_user_logout(sender, request, user, **kwargs):
    """Log when a user logs out."""
    if user:
        ip_address = request.META.get('REMOTE_ADDR', None)
        log_activity(
            user=user,
            action="User Logged Out",
            category=ActivityLog.Category.USER,
            action_type=ActivityLog.ActionType.LOGOUT,
            branch=user.branch,
            ip_address=ip_address
        )
