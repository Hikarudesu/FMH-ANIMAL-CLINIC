"""Service layer for POS (Point of Sale) business logic."""

from datetime import date
from decimal import Decimal

from django.db import transaction

from billing.models import CustomerStatement
from notifications.utils import notify_statement_released
from .models import Sale


def _build_statement_from_sale(sale: Sale) -> CustomerStatement:
    owner_name = sale.customer.get_full_name().strip() if sale.customer else ''
    if not owner_name:
        owner_name = sale.customer_display_name

    patient_name = sale.pet.name if sale.pet else 'General Services'

    return CustomerStatement.objects.create(
        patient_name=patient_name[:100],
        owner_name=owner_name[:200],
        date=date.today(),
        customer=sale.customer,
        sale=sale,
        consultation_fee=Decimal('0.00'),
        treatment=Decimal('0.00'),
        boarding=Decimal('0.00'),
        vaccination=Decimal('0.00'),
        surgery=Decimal('0.00'),
        laboratory=Decimal('0.00'),
        grooming=Decimal('0.00'),
        others=sale.total,
        others_description=f'POS Transaction {sale.transaction_id}',
        total_amount=sale.total,
        deposit=sale.amount_paid,
        status='RELEASED',
        created_by=sale.cashier,
        branch=sale.branch,
    )


def create_or_release_soa_for_sale(sale: Sale) -> CustomerStatement | None:
    """
    Create/release SOA from completed sale for registered owners.
    Returns the released CustomerStatement, else None.
    """
    if sale.status != Sale.Status.COMPLETED or not sale.customer:
        return None

    with transaction.atomic():
        statement = CustomerStatement.objects.filter(sale=sale).first()
        if statement is None:
            statement = _build_statement_from_sale(sale)
        elif statement.status == 'DRAFT':
            statement.status = 'RELEASED'
            statement.save(update_fields=['status'])

        notify_statement_released(statement)
        return statement
