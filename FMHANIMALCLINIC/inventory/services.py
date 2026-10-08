"""Services for recurring inventory operations."""
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from notifications.models import Notification
from notifications.utils import notify_reservation_status
from .models import Reservation, StockAdjustment


def auto_cancel_expired_reservations():
    """Cancel pending reservations after their 24-hour pickup grace period."""
    expiration_threshold = timezone.now() - timedelta(hours=24)
    pickup_date_threshold = timezone.localdate() - timedelta(days=2)
    expired_reservations = Reservation.objects.filter(
        status=Reservation.Status.PENDING,
    ).filter(
        Q(pickup_date__isnull=True, created_at__lte=expiration_threshold)
        | Q(pickup_date__isnull=False, pickup_date__lte=pickup_date_threshold)
    ).select_related('product', 'product__branch', 'user')

    cancelled_count = 0
    for reservation in expired_reservations:
        reservation.status = Reservation.Status.CANCELLED
        reservation.save(update_fields=['status', 'updated_at'])
        StockAdjustment.objects.create(
            branch=reservation.product.branch,
            product=reservation.product,
            adjustment_type='ADD',
            reference=f'RSV-{reservation.pk}-AUTO-EXP',
            date=timezone.localdate(),
            quantity=reservation.quantity,
            cost_per_unit=reservation.product.unit_cost,
            reason='Automatically cancelled 24 hours after pickup date.',
        )
        notify_reservation_status(
            reservation,
            title='Reservation Expired',
            message=(
                f'Your reservation for {reservation.quantity}x {reservation.product.name} '
                f'({reservation.product.sale_type_label}, {reservation.product.unit_display}) '
                'has expired and was cancelled.'
            ),
            notification_type=Notification.NotificationType.PRODUCT_RESERVATION,
        )
        cancelled_count += 1

    return cancelled_count
