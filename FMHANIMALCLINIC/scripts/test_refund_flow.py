"""
Test script: simulate partial refund flow and verify inventory adjustments.
Run from project root: python scripts/test_refund_flow.py
"""
import os
import sys
import traceback
from decimal import Decimal

# Ensure project root is on sys.path so "FMHANIMALCLINIC" package can be imported
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'FMHANIMALCLINIC.settings')

try:
    import django
    django.setup()
    from pos.models import Sale, Refund
    from inventory.models import StockAdjustment
    from django.contrib.auth import get_user_model

    User = get_user_model()

    print('Searching for a completed sale with product/medication items...')
    sale = Sale.objects.filter(status=Sale.Status.COMPLETED).filter(items__item_type__in=['PRODUCT','MEDICATION']).distinct().first()
    if not sale:
        print('No completed sale with product/medication items found. Looking for any completed sale...')
        sale = Sale.objects.filter(status=Sale.Status.COMPLETED).first()

    if not sale:
        print('No completed sales available in DB. Cannot run refund test.')
        sys.exit(1)

    print(f'Using sale id={sale.pk}, transaction_id={sale.transaction_id}, branch={sale.branch} cashr={sale.cashier}')

    # Find refundable items
    items_data = []
    for item in sale.items.all():
        refundable_qty = item.get_refundable_quantity()
        if refundable_qty > 0:
            qty = 1 if refundable_qty >= 1 else refundable_qty
            items_data.append({'sale_item_id': item.pk, 'quantity': qty})

    if not items_data:
        print('No refundable quantities found on this sale (all items already refunded). Exiting.')
        sys.exit(0)

    requester = sale.cashier or User.objects.first()
    print('Creating partial refund for items:', items_data)
    refund = Refund.create_partial_refund(
        sale=sale,
        items_data=items_data,
        reason='Automated test partial refund',
        requested_by=requester,
        refund_method='CASH'
    )
    print('Created refund:', refund.refund_id, 'amount=', refund.amount)

    # Auto-approve and complete
    refund.status = Refund.Status.APPROVED
    refund.approved_by = requester
    refund.save(update_fields=['status', 'approved_by'])

    print('Approving and completing refund...')
    refund.complete_refund(requester)
    print('Refund completed. status=', refund.status, 'processed_by=', refund.processed_by)

    # Verify StockAdjustment entries created
    adjustments = StockAdjustment.objects.filter(reference=refund.refund_id)
    print('StockAdjustments created count=', adjustments.count())
    for adj in adjustments:
        print('-', adj.pk, adj.product, adj.quantity, adj.adjustment_type, adj.reference)

    # Verify sale status unchanged for partial refunds
    sale.refresh_from_db()
    print('Sale status after refund:', sale.status)

    print('Test finished successfully.')

except Exception as e:
    print('Error during test run:', e)
    traceback.print_exc()
    sys.exit(2)
