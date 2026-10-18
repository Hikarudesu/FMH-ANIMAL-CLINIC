from django.conf import settings
from django.db import migrations, models
from django.db.models import Q


PRIMARY_TYPES = [
    'FOLLOW_UP',
    'FOLLOW_UP_OVERDUE',
    'MEDICAL_RECORD_UPDATE',
    'LOW_INVENTORY',
    'INVENTORY_EXPIRY_ALERT',
    'LOW_STOCK_ALERT',
    'INQUIRY_NEW',
    'STOCK_TRANSFER_REQUESTED',
    'STATEMENT_RELEASED',
    'PAYROLL_GENERATED',
    'PAYROLL_RELEASED',
    'RESERVATION_READY',
    'RESERVATION_REJECTED',
]


def classify_existing_notifications(apps, schema_editor):
    Notification = apps.get_model('notifications', 'Notification')
    Notification.objects.all().update(inbox_category='UPDATES')
    Notification.objects.filter(notification_type__in=PRIMARY_TYPES).update(
        inbox_category='PRIMARY'
    )
    Notification.objects.filter(
        notification_type='APPOINTMENT',
    ).filter(
        Q(user__is_superuser=True) | Q(user__assigned_role__is_staff_role=True)
    ).update(inbox_category='PRIMARY')
    Notification.objects.filter(
        notification_type__in=['APPOINTMENT_CANCELLED', 'APPOINTMENT_RESCHEDULED'],
    ).filter(
        Q(user__is_superuser=False, user__assigned_role__isnull=True)
        | Q(user__assigned_role__is_staff_role=False, user__is_superuser=False)
    ).update(inbox_category='PRIMARY')


class Migration(migrations.Migration):

    dependencies = [
        ('notifications', '0012_followup_medical_record_reminder'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='notification',
            name='inbox_category',
            field=models.CharField(
                choices=[('PRIMARY', 'Primary'), ('UPDATES', 'Updates')],
                default='UPDATES',
                max_length=10,
            ),
        ),
        migrations.RunPython(
            classify_existing_notifications,
            migrations.RunPython.noop,
        ),
    ]
