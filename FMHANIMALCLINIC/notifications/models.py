from django.db import models
from django.conf import settings


class FollowUp(models.Model):
    """Represents a follow-up visit scheduled by an admin for a pet."""

    appointment = models.ForeignKey(
        'appointments.Appointment',
        on_delete=models.CASCADE,
        related_name='follow_ups',
    )
    pet_name = models.CharField(
        max_length=150, help_text='Denormalized for easy display')
    follow_up_date = models.DateField(verbose_name="Start Date")
    follow_up_end_date = models.DateField(
        null=True, blank=True, verbose_name="End Date",
        help_text="Optional end date for a follow-up range"
    )
    reason = models.TextField(
        blank=True, help_text='Reason for the return visit')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_follow_ups',
    )
    is_completed = models.BooleanField(default=False)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['follow_up_date']

    def __str__(self):
        if self.follow_up_end_date and self.follow_up_end_date != self.follow_up_date:
            return f'Follow-up: {self.pet_name} from {self.follow_up_date} to {self.follow_up_end_date}'
        return f'Follow-up: {self.pet_name} on {self.follow_up_date}'


class Notification(models.Model):
    """User-facing notification record."""

    class ModuleContext(models.TextChoices):
        APPOINTMENTS = 'appointments', 'Appointments'
        PATIENTS = 'patients', 'Patients'
        MEDICAL_RECORDS = 'medical_records', 'Medical Records'
        AI_DIAGNOSTICS = 'ai_diagnostics', 'AI Diagnostics'
        INVENTORY = 'inventory', 'Inventory'
        SOA = 'soa', 'Statement of Account'
        NOTIFICATIONS = 'notifications', 'Notifications'
        GENERAL = 'general', 'General'

    class NotificationType(models.TextChoices):
        FOLLOW_UP = 'FOLLOW_UP', 'Follow-up'
        APPOINTMENT = 'APPOINTMENT', 'Appointment'
        APPOINTMENT_CONFIRMED = 'APPOINTMENT_CONFIRMED', 'Appointment Confirmed'
        APPOINTMENT_CANCELLED = 'APPOINTMENT_CANCELLED', 'Appointment Cancelled'
        APPOINTMENT_RESCHEDULED = 'APPOINTMENT_RESCHEDULED', 'Appointment Rescheduled'
        RESERVATION_APPROVED = 'RESERVATION_APPROVED', 'Reservation Approved'
        RESERVATION_REJECTED = 'RESERVATION_REJECTED', 'Reservation Rejected'
        RESERVATION_READY = 'RESERVATION_READY', 'Reservation Ready'
        FOLLOW_UP_OVERDUE = 'FOLLOW_UP_OVERDUE', 'Follow-up Overdue'
        INVENTORY_RESTOCK = 'INVENTORY_RESTOCK', 'Inventory Restock'
        LOW_INVENTORY = 'LOW_INVENTORY', 'Low Inventory'
        LOW_STOCK_ALERT = 'LOW_STOCK_ALERT', 'Low Stock Alert'
        PRODUCT_RESERVATION = 'PRODUCT_RESERVATION', 'Product Reservation'
        STATEMENT_RELEASED = 'STATEMENT_RELEASED', 'Statement Released'
        MEDICAL_RECORD_UPDATE = 'MEDICAL_RECORD_UPDATE', 'Medical Record Update'
        GENERAL = 'GENERAL', 'General'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications',
    )
    title = models.CharField(max_length=200)
    message = models.TextField()
    notification_type = models.CharField(
        max_length=30,
        choices=NotificationType.choices,
        default=NotificationType.GENERAL,
    )
    module_context = models.CharField(
        max_length=30,
        choices=ModuleContext.choices,
        default=ModuleContext.GENERAL,
        help_text='Module scope used for RBAC filtering.',
    )
    related_follow_up = models.ForeignKey(
        FollowUp,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='notifications',
    )
    related_object_id = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="ID of the related object (e.g., Appointment ID or Product ID)"
    )
    is_read = models.BooleanField(default=False)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'is_read']),
            models.Index(fields=['user', 'created_at']),
            models.Index(fields=['notification_type']),
        ]

    def __str__(self):
        return f'{self.title} — {self.user.username}'

    @classmethod
    def scoped_for_user(cls, user):
        """Return notifications visible to the current user under module RBAC."""
        queryset = cls.objects.filter(user=user)
        if user.is_superuser:
            return queryset

        if user.is_pet_owner():
            return queryset.filter(
                module_context__in=[
                    cls.ModuleContext.APPOINTMENTS,
                    cls.ModuleContext.PATIENTS,
                    cls.ModuleContext.SOA,
                    cls.ModuleContext.NOTIFICATIONS,
                    cls.ModuleContext.GENERAL,
                ]
            )

        if user.assigned_role:
            allowed_module_codes = set(
                user.assigned_role.module_permissions.values_list('module__code', flat=True)
            )
            allowed_module_codes.update(
                ['notifications', cls.ModuleContext.GENERAL]
            )
            return queryset.filter(module_context__in=allowed_module_codes)

        return queryset.none()
