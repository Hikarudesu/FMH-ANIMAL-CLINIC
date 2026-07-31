"""
Test script: simulate partial refund flow for a specific transaction_id and verify inventory adjustments.
Usage: edit TRANSACTION_ID below and run: python scripts/test_refund_specific.py
"""
import os
import sys
import traceback

TRANSACTION_ID = 'TXN202607303D9F46'  # target - edit if needed

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'FMHANIMALCLINIC.settings')

# Ensure project root is on sys.path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

try:
    import django
    django.setup()
    from pos.models import Sale, Refund
    from inventory.models import StockAdjustment
    from django.contrib.auth import get_user_model

    User = get_user_model()

    print('Looking up sale with transaction_id=', TRANSACTION_ID)
    try:
        sale = Sale.objects.get(transaction_id=TRANSACTION_ID)
    except Sale.DoesNotExist:
        print('Sale not found')
        sys.exit(1)

    print(f'Found sale id={sale.pk}, status={sale.status}, branch={sale.branch}, cashier={sale.cashier}')

    if sale.status != Sale.Status.COMPLETED:
        print('Sale is not completed; cannot refund. Current status:', sale.status)
        sys.exit(1)

    # Build refundable items
    items_data = []
    for item in sale.items.all():
        refundable_qty = item.get_refundable_quantity()
        if refundable_qty > 0:
            qty = 1 if refundable_qty >= 1 else refundable_qty
            items_data.append({'sale_item_id': item.pk, 'quantity': qty})

    if not items_data:
        print('No refundable quantities available for this sale.')
        sys.exit(0)

    requester = sale.cashier or User.objects.first()
    print('Creating partial refund for items:', items_data)
    refund = Refund.create_partial_refund(
        sale=sale,
        items_data=items_data,
        reason='Automated test partial refund (specific TXN)',
        requested_by=requester,
        refund_method='CASH'
    )
    print('Created refund:', refund.refund_id, 'amount=', refund.amount)

    refund.status = Refund.Status.APPROVED
    refund.approved_by = requester
    refund.save(update_fields=['status', 'approved_by'])

    print('Approving and completing refund...')
    refund.complete_refund(requester)
    print('Refund completed. status=', refund.status, 'processed_by=', refund.processed_by)

    adjustments = StockAdjustment.objects.filter(reference=refund.refund_id)
    print('StockAdjustments created count=', adjustments.count())
    for adj in adjustments:
        print('-', adj.pk, adj.product, adj.quantity, adj.adjustment_type, adj.reference)

    sale.refresh_from_db()
    print('Sale status after refund:', sale.status)

    print('Specific TXN test finished successfully.')

except Exception as e:
    print('Error during test run:', e)
    traceback.print_exc()
    sys.exit(2)
