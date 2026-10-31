from django.db import models
from django.conf import settings


MODULE_NOTIFICATION_CONTEXT_ALIASES = {
    'reservations': {'inventory'},
    'stock_monitor': {'inventory'},
    'stock_transfers': {'inventory'},
}

SPECIAL_PERMISSION_NOTIFICATION_CONTEXTS = {
    'can_access_stock_monitor': {'inventory'},
    'can_request_stock_transfer': {'inventory'},
    'can_view_own_payslips': {'payroll'},
    'can_access_pos': {'soa'},
}

SPECIAL_PERMISSION_MODULE_ACCESS = {
    'inventory': ('can_access_stock_monitor', 'can_request_stock_transfer'),
    'stock_monitor': ('can_access_stock_monitor',),
    'stock_transfers': ('can_request_stock_transfer',),
    'soa': ('can_access_pos',),
}

BRANCH_SCOPED_SPECIAL_PERMISSION_MODULE_ACCESS = {
    'inventory': ('can_access_stock_monitor', 'can_request_stock_transfer'),
    'stock_monitor': ('can_access_stock_monitor',),
    'stock_transfers': ('can_request_stock_transfer',),
    'soa': ('can_access_pos',),
}

NOTIFICATION_CONTEXT_MODULES = {
    'appointments': 'appointments',
    'patients': 'patients',
    'medical_records': 'medical_records',
    'ai_diagnostics': 'ai_diagnostics',
    'inventory': 'inventory',
    'soa': 'soa',
    'inquiries': 'inquiries',
    'payroll': 'payroll',
}

MODULE_ALIAS_NOTIFICATION_TYPES = {
    'reservations': {
        'GENERAL',
        'PRODUCT_RESERVATION',
        'RESERVATION_APPROVED',
        'RESERVATION_REJECTED',
        'RESERVATION_READY',
    },
    'stock_monitor': {
        'GENERAL',
        'LOW_INVENTORY',
        'LOW_STOCK_ALERT',
        'INVENTORY_EXPIRY_ALERT',
    },
    'stock_transfers': {
        'GENERAL',
        'STOCK_TRANSFER_REQUESTED',
        'STOCK_TRANSFER_APPROVED',
        'STOCK_TRANSFER_REJECTED',
        'STOCK_TRANSFER_COMPLETED',
    },
}

SPECIAL_PERMISSION_NOTIFICATION_TYPES = {
    'can_access_stock_monitor': MODULE_ALIAS_NOTIFICATION_TYPES['stock_monitor'],
    'can_request_stock_transfer': MODULE_ALIAS_NOTIFICATION_TYPES['stock_transfers'],
    'can_view_own_payslips': {'GENERAL', 'PAYROLL_RELEASED'},
    'can_access_pos': {'GENERAL', 'STATEMENT_RELEASED'},
}


class FollowUp(models.Model):
    """Represents a recommended return visit, separate from its booking."""

    appointment = models.ForeignKey(
        'appointments.Appointment',
        on_delete=models.CASCADE,
        related_name='follow_ups',
        null=True,
        blank=True,
    )
    booked_appointment = models.ForeignKey(
        'appointments.Appointment',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='originating_follow_ups',
        help_text='Separate appointment booked in response to this follow-up.',
    )
    medical_record = models.ForeignKey(
        'records.MedicalRecord',
        on_delete=models.CASCADE,
        related_name='follow_up_schedule',
        null=True,
        blank=True,
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
    is_expired = models.BooleanField(default=False)
    expiration_reason = models.TextField(blank=True)
    email_sent_at = models.DateTimeField(null=True, blank=True)
    reminder_email_sent_at = models.DateTimeField(null=True, blank=True)
    email_attempts = models.PositiveIntegerField(default=0)
    email_last_error = models.TextField(blank=True)

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
        INQUIRIES = 'inquiries', 'Inquiries'
        PAYROLL = 'payroll', 'Payroll'
        NOTIFICATIONS = 'notifications', 'Notifications'
        GENERAL = 'general', 'General'

    class NotificationType(models.TextChoices):
        FOLLOW_UP = 'FOLLOW_UP', 'Follow-up'
        APPOINTMENT = 'APPOINTMENT', 'Appointment'
        APPOINTMENT_CONFIRMED = 'APPOINTMENT_CONFIRMED', 'Appointment Confirmed'
        APPOINTMENT_CANCELLED = 'APPOINTMENT_CANCELLED', 'Appointment Cancelled'
        APPOINTMENT_RESCHEDULED = 'APPOINTMENT_RESCHEDULED', 'Appointment Rescheduled'
        APPOINTMENT_REMINDER_1 = 'APPOINTMENT_REMINDER_1', 'Appointment Reminder (1 Day)'
        APPOINTMENT_REMINDER_2 = 'APPOINTMENT_REMINDER_2', 'Appointment Reminder (3 Hours)'
        RESERVATION_APPROVED = 'RESERVATION_APPROVED', 'Reservation Approved'
        RESERVATION_REJECTED = 'RESERVATION_REJECTED', 'Reservation Rejected'
        RESERVATION_READY = 'RESERVATION_READY', 'Reservation Ready'
        FOLLOW_UP_OVERDUE = 'FOLLOW_UP_OVERDUE', 'Follow-up Overdue'
        INVENTORY_RESTOCK = 'INVENTORY_RESTOCK', 'Inventory Restock'
        LOW_INVENTORY = 'LOW_INVENTORY', 'Low Inventory'
        INVENTORY_EXPIRY_ALERT = 'INVENTORY_EXPIRY_ALERT', 'Inventory Expiry Alert'
        LOW_STOCK_ALERT = 'LOW_STOCK_ALERT', 'Low Stock Alert'
        PRODUCT_RESERVATION = 'PRODUCT_RESERVATION', 'Product Reservation'
        STATEMENT_RELEASED = 'STATEMENT_RELEASED', 'Statement Released'
        MEDICAL_RECORD_UPDATE = 'MEDICAL_RECORD_UPDATE', 'Medical Record Update'
        PATIENT_UPDATED = 'PATIENT_UPDATED', 'Pet Profile Updated'
        PATIENT_ARCHIVED = 'PATIENT_ARCHIVED', 'Pet Profile Archived'
        PATIENT_CREATED = 'PATIENT_CREATED', 'Pet Profile Added'
        INQUIRY_NEW = 'INQUIRY_NEW', 'New Inquiry'
        INQUIRY_RESPONDED = 'INQUIRY_RESPONDED', 'Inquiry Responded'
        INQUIRY_ARCHIVED = 'INQUIRY_ARCHIVED', 'Inquiry Archived'
        STOCK_TRANSFER_REQUESTED = 'STOCK_TRANSFER_REQUESTED', 'Stock Transfer Requested'
        STOCK_TRANSFER_APPROVED = 'STOCK_TRANSFER_APPROVED', 'Stock Transfer Approved'
        STOCK_TRANSFER_REJECTED = 'STOCK_TRANSFER_REJECTED', 'Stock Transfer Rejected'
        STOCK_TRANSFER_COMPLETED = 'STOCK_TRANSFER_COMPLETED', 'Stock Transfer Completed'
        PAYROLL_GENERATED = 'PAYROLL_GENERATED', 'Payroll Generated'
        PAYROLL_RELEASED = 'PAYROLL_RELEASED', 'Payroll Released'
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
    def visible_module_contexts_for_user(cls, user):
        """Return module contexts that should be visible to the given user."""
<<<<<<< HEAD
        from accounts.rbac_models import Module
        from accounts.rbac_constants import HierarchyLevels

        def notification_contexts(module_codes):
            contexts = set(module_codes)
            for module_code in module_codes:
                contexts.update(
                    MODULE_NOTIFICATION_CONTEXT_ALIASES.get(module_code, ())
                )
            return contexts

        if user.is_superuser:
            accessible_modules = set(
                Module.objects.filter(is_active=True).values_list('code', flat=True)
            )
            visible_contexts = notification_contexts(accessible_modules)
            visible_contexts.update(['notifications', cls.ModuleContext.GENERAL])
            return visible_contexts
=======
        if user.is_superuser:
            # Superadmins must see system events even when a module is hidden
            # from navigation or its RBAC row is not present.
            return {
                context.value
                for context in cls.ModuleContext
            } | {'notifications'}
>>>>>>> f5ce28ea1168901cb70e0cde2cbe6cc33794e49f

        if user.is_pet_owner():
            return {
                cls.ModuleContext.APPOINTMENTS,
                cls.ModuleContext.PATIENTS,
                cls.ModuleContext.MEDICAL_RECORDS,
                cls.ModuleContext.SOA,
                cls.ModuleContext.INVENTORY,
                cls.ModuleContext.NOTIFICATIONS,
                cls.ModuleContext.GENERAL,
            }

        if user.assigned_role:
            from accounts.rbac_constants import HierarchyLevels

            if user.assigned_role.hierarchy_level >= HierarchyLevels.ADMIN:
                accessible_modules = set(
                    Module.objects.filter(is_active=True).values_list('code', flat=True)
                )
            else:
                accessible_modules = set(
                    user.assigned_role.module_permissions.filter(
                        module__is_active=True,
                    ).values_list('module__code', flat=True)
                )
            visible_contexts = notification_contexts(accessible_modules)
            special_permission_codes = user.assigned_role.special_permissions.values_list(
                'permission__code', flat=True,
            )
            for permission_code in special_permission_codes:
                visible_contexts.update(
                    SPECIAL_PERMISSION_NOTIFICATION_CONTEXTS.get(permission_code, ())
                )
            # Cashiers handle appointment intake and must see appointment
            # notifications even for databases with older role permissions.
            if user.assigned_role.code in ('cashier', 'receptionist'):
                visible_contexts.add(cls.ModuleContext.APPOINTMENTS)
            visible_contexts.update(['notifications', cls.ModuleContext.GENERAL])
            return visible_contexts

        return set()

    @classmethod
    def scoped_for_user(cls, user):
        """Return notifications visible to the current user under module RBAC."""
        queryset = cls.objects.filter(user=user)
        visible_module_contexts = cls.visible_module_contexts_for_user(user)
        if not visible_module_contexts:
            return queryset.none()
        queryset = queryset.filter(module_context__in=visible_module_contexts)
        type_restrictions = cls.notification_type_restrictions_for_user(user)
        if type_restrictions:
            allowed_alias_notifications = models.Q(pk__in=[])
            for module_context, notification_types in type_restrictions.items():
                allowed_alias_notifications |= models.Q(
                    module_context=module_context,
                    notification_type__in=notification_types,
                )
            queryset = queryset.filter(
                ~models.Q(module_context__in=type_restrictions)
                | allowed_alias_notifications
            )
        return queryset

    @classmethod
    def notification_type_restrictions_for_user(cls, user):
        """Limit aliased contexts to the event types belonging to each access path."""
        if user.is_superuser:
            return {}

        if user.is_pet_owner():
            return {
                cls.ModuleContext.INVENTORY: MODULE_ALIAS_NOTIFICATION_TYPES['reservations'],
            }

        role = user.assigned_role
        if not role:
            return {}

        from accounts.rbac_constants import HierarchyLevels

        if role.hierarchy_level >= HierarchyLevels.ADMIN:
            return {}

        module_codes = set(
            role.module_permissions.filter(
                module__is_active=True,
            ).values_list('module__code', flat=True)
        )
        special_codes = set(
            role.special_permissions.values_list('permission__code', flat=True)
        )
        restrictions = {}

        if 'inventory' not in module_codes:
            inventory_types = set()
            for module_code, notification_types in MODULE_ALIAS_NOTIFICATION_TYPES.items():
                if module_code in module_codes:
                    inventory_types.update(notification_types)
            for permission_code in special_codes:
                inventory_types.update(
                    SPECIAL_PERMISSION_NOTIFICATION_TYPES.get(permission_code, ())
                )
            if inventory_types:
                restrictions[cls.ModuleContext.INVENTORY] = inventory_types

        if 'payroll' not in module_codes and 'can_view_own_payslips' in special_codes:
            restrictions[cls.ModuleContext.PAYROLL] = {'PAYROLL_RELEASED'}

        if 'soa' not in module_codes and 'can_access_pos' in special_codes:
            restrictions[cls.ModuleContext.SOA] = {'STATEMENT_RELEASED'}

        return restrictions
