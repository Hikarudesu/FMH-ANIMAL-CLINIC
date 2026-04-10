"""Views for POS module."""

from decimal import Decimal, InvalidOperation

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_GET
from django.db.models import Q, Sum
from django.db import transaction
from django.core.paginator import Paginator

from accounts.decorators import module_permission_required, special_permission_required
from accounts.models import User
from billing.models import Service
from branches.models import Branch
from inventory.models import Product
from patients.models import Pet

from .models import Sale, SaleItem, Payment, Refund
from .forms import RefundForm
from .services import create_or_release_soa_for_sale


# =============================================================================
# POS Checkout Interface
# =============================================================================

@login_required
@special_permission_required('can_access_pos')
def checkout(request):
    """Main POS checkout interface."""
    branch = request.user.branch

    # Create new pending sale or get existing one
    pending_sale = Sale.objects.filter(
        branch=branch,
        cashier=request.user,
        status=Sale.Status.PENDING
    ).first()

    if not pending_sale:
        with transaction.atomic():
            pending_sale = Sale.objects.create(
                branch=branch,
                cashier=request.user
            )

    # Get available items for the branch
    services = Service.objects.filter(
        Q(branch=branch) | Q(branch__isnull=True),
        active=True
    ).order_by('category', 'name')

    # POS users are always branch-restricted (no dropdown)
    # Only show items from their assigned branch
    branches = []  # Hide branch dropdown for POS users
    
    # Products filtered to user's branch only
    if branch:
        products = Product.objects.filter(
            branch=branch,
            stock_quantity__gt=0
        ).exclude(item_type='Services').order_by('name')
        
        medications = Product.objects.filter(
            branch=branch,
            item_type='Medication',
            stock_quantity__gt=0
        ).order_by('name')
    else:
        products = Product.objects.none()
        medications = Product.objects.none()

    # Get customers for dropdown (pet owners = not staff or no role)
    customers = User.objects.filter(
        is_active=True
    ).filter(
        Q(assigned_role__is_staff_role=False) | Q(assigned_role__isnull=True)
    ).order_by('first_name', 'last_name')

    context = {
        'sale': pending_sale,
        'items': pending_sale.items.all(),
        'services': services,
        'products': products,
        'medications': medications,
        'customers': customers,
        'branches': branches,
        'payment_methods': Payment.Method.choices,
        'is_branch_restricted': True,  # POS is always branch-restricted
    }
    return render(request, 'pos/checkout.html', context)


@login_required
@special_permission_required('can_access_pos')
@require_POST
def add_item(request):
    """Add an item to the current sale via AJAX."""
    sale_id = request.POST.get('sale_id')
    item_type = request.POST.get('item_type')
    item_id = request.POST.get('item_id')
    quantity = int(request.POST.get('quantity', 1))

    try:
        sale = Sale.objects.get(pk=sale_id, status=Sale.Status.PENDING)
    except Sale.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Sale not found'}, status=404)

    with transaction.atomic():
        # Get the item based on type
        if item_type == 'SERVICE':
            try:
                item = Service.objects.get(pk=item_id, active=True)
                existing_item = sale.items.filter(item_type=SaleItem.ItemType.SERVICE, service=item).first()
                if existing_item:
                    existing_item.quantity += quantity
                    existing_item.save()
                    sale_item = existing_item
                else:
                    sale_item = SaleItem.objects.create(
                        sale=sale,
                        item_type=SaleItem.ItemType.SERVICE,
                        service=item,
                        name=item.name,
                        unit_price=item.price,
                        quantity=quantity
                    )
            except Service.DoesNotExist:
                return JsonResponse({'success': False, 'error': 'Service not found'}, status=404)

        elif item_type in ['PRODUCT', 'MEDICATION']:
            try:
                item = Product.objects.get(pk=item_id, is_available=True)
                existing_item = sale.items.filter(item_type=item_type, product=item).first()
                new_quantity = (existing_item.quantity if existing_item else 0) + quantity

                if item.stock_quantity < new_quantity:
                    return JsonResponse({
                        'success': False,
                        'error': f'Insufficient stock. Available: {item.stock_quantity}'
                    }, status=400)

                if existing_item:
                    existing_item.quantity = new_quantity
                    existing_item.save()
                    sale_item = existing_item
                else:
                    sale_item = SaleItem.objects.create(
                        sale=sale,
                        item_type=item_type,
                        product=item,
                        name=item.name,
                        unit_price=item.price,
                        quantity=quantity
                    )
            except Product.DoesNotExist:
                return JsonResponse({'success': False, 'error': 'Product not found'}, status=404)
        else:
            return JsonResponse({'success': False, 'error': 'Invalid item type'}, status=400)

    return JsonResponse({
        'success': True,
        'item': {
            'id': sale_item.pk,
            'name': sale_item.name,
            'quantity': sale_item.quantity,
            'unit_price': str(sale_item.unit_price),
            'line_total': str(sale_item.line_total),
        },
        'sale': {
            'subtotal': str(sale.subtotal),
            'total': str(sale.total),
        }
    })


@login_required
@special_permission_required('can_access_pos')
@require_POST
def remove_item(request):
    """Remove an item from the sale via AJAX."""
    item_id = request.POST.get('item_id')

    try:
        item = SaleItem.objects.get(pk=item_id)
        sale = item.sale
        item.delete()
        sale.calculate_totals()
    except SaleItem.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Item not found'}, status=404)

    return JsonResponse({
        'success': True,
        'sale': {
            'subtotal': str(sale.subtotal),
            'total': str(sale.total),
        }
    })


@login_required
@special_permission_required('can_access_pos')
@require_POST
def update_item_quantity(request):
    """Update item quantity via AJAX."""
    item_id = request.POST.get('item_id')
    quantity = int(request.POST.get('quantity', 1))

    try:
        item = SaleItem.objects.get(pk=item_id)

        # Check stock for products
        if item.item_type in ['PRODUCT', 'MEDICATION'] and item.product:
            if item.product.stock_quantity < quantity:
                return JsonResponse({
                    'success': False,
                    'error': f'Insufficient stock. Available: {item.product.stock_quantity}'
                }, status=400)

        item.quantity = quantity
        item.save()
        sale = item.sale

    except SaleItem.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Item not found'}, status=404)

    return JsonResponse({
        'success': True,
        'item': {
            'id': item.pk,
            'quantity': item.quantity,
            'line_total': str(item.line_total),
        },
        'sale': {
            'subtotal': str(sale.subtotal),
            'total': str(sale.total),
        }
    })


@login_required
@special_permission_required('can_access_pos')
@require_POST
def update_sale_info(request):
    """Update sale customer info and discount via AJAX."""
    sale_id = request.POST.get('sale_id')

    try:
        sale = Sale.objects.get(pk=sale_id, status=Sale.Status.PENDING)
    except Sale.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Sale not found'}, status=404)

    # Track which fields to save
    update_fields = ['customer_type', 'guest_name', 'guest_phone', 'guest_email', 'notes']

    # Update customer info
    customer_type = request.POST.get('customer_type', 'WALKIN')
    sale.customer_type = customer_type

    if customer_type == 'REGISTERED':
        customer_id = request.POST.get('customer_id')
        if customer_id:
            try:
                sale.customer = User.objects.get(pk=customer_id)
                # Auto-fill guest fields from customer
                sale.guest_name = sale.customer.get_full_name()
                sale.guest_phone = getattr(sale.customer, 'phone_number', '') or ''
                sale.guest_email = sale.customer.email
                update_fields.append('customer')
            except User.DoesNotExist:
                pass
        pet_id = request.POST.get('pet_id')
        if pet_id:
            try:
                sale.pet = Pet.objects.get(pk=pet_id)
                update_fields.append('pet')
            except Pet.DoesNotExist:
                pass
    else:
        sale.customer = None
        sale.guest_name = request.POST.get('guest_name', '')
        sale.guest_phone = request.POST.get('guest_phone', '')
        sale.guest_email = request.POST.get('guest_email', '')
        update_fields.append('customer')

    # ONLY update discount if discount_percent is explicitly provided in POST
    # This prevents the payment flow from accidentally wiping the discount
    if 'discount_percent' in request.POST:
        discount_pct = request.POST.get('discount_percent', '0')
        discount_reason = request.POST.get('discount_reason', '').strip()
        try:
            discount_pct_value = Decimal(str(discount_pct)) if discount_pct else Decimal('0.00')
            # Clamp between 0-100
            discount_pct_value = max(Decimal('0'), min(Decimal('100'), discount_pct_value))
        except (ValueError, InvalidOperation):
            discount_pct_value = Decimal('0.00')

        # Require reason if discount is applied
        if discount_pct_value > 0 and not discount_reason:
            return JsonResponse({
                'success': False,
                'error': 'Discount reason is required when applying a discount.'
            }, status=400)

        sale.discount_percent = discount_pct_value
        sale.discount_reason = discount_reason
        update_fields.extend(['discount_percent', 'discount_reason'])

    sale.notes = request.POST.get('notes', '')

    # Save only the fields that were updated
    sale.save(update_fields=update_fields)

    # Calculate totals (will refresh discount_percent from DB before calculating)
    sale.calculate_totals()

    # Refresh to get final values
    sale.refresh_from_db()

    return JsonResponse({
        'success': True,
        'sale': {
            'subtotal': str(sale.subtotal),
            'discount_percent': str(sale.discount_percent),
            'discount_amount': str(sale.discount_amount),
            'discount_reason': sale.discount_reason or '',
            'total': str(sale.total),
        }
    })


@login_required
@special_permission_required('can_access_pos')
@require_POST
def process_payment(request):
    """Process payment for a sale."""
    sale_id = request.POST.get('sale_id')
    method = request.POST.get('method')
    amount = Decimal(request.POST.get('amount', '0'))
    reference = request.POST.get('reference_number', '')

    try:
        sale = Sale.objects.get(pk=sale_id, status=Sale.Status.PENDING)
    except Sale.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Sale not found'}, status=404)

    if not sale.items.exists():
        return JsonResponse({'success': False, 'error': 'Cannot process empty sale'}, status=400)

    with transaction.atomic():
        Payment.objects.create(
            sale=sale,
            method=method,
            amount=amount,
            reference_number=reference,
            received_by=request.user
        )

        if sale.is_fully_paid:
            sale.complete_sale()
            create_or_release_soa_for_sale(sale)

            return JsonResponse({
                'success': True,
                'completed': True,
                'sale': {
                    'transaction_id': sale.transaction_id,
                    'total': str(sale.total),
                    'amount_paid': str(sale.amount_paid),
                    'change_due': str(sale.change_due),
                }
            })

    return JsonResponse({
        'success': True,
        'completed': False,
        'sale': {
            'total': str(sale.total),
            'amount_paid': str(sale.amount_paid),
            'balance_due': str(sale.balance_due),
        }
    })


@login_required
@special_permission_required('can_access_pos')
@require_POST
def void_sale(request, sale_id):
    """Void a sale."""
    try:
        sale = Sale.objects.get(pk=sale_id)
    except Sale.DoesNotExist:
        messages.error(request, 'Sale not found.')
        return redirect('pos:sales_list')

    reason = request.POST.get('reason', '')
    try:
        sale.void_sale(request.user, reason)
        messages.success(request, f'Sale {sale.transaction_id} has been voided.')
    except ValueError as e:
        messages.error(request, str(e))

    return redirect('pos:sales_list')


@login_required
@special_permission_required('can_access_pos')
def cancel_sale(request, sale_id):
    """Cancel a pending sale (delete it)."""
    try:
        sale = Sale.objects.get(pk=sale_id, status=Sale.Status.PENDING)
        sale.delete()
        messages.info(request, 'Sale cancelled.')
    except Sale.DoesNotExist:
        messages.error(request, 'Sale not found or already completed.')

    return redirect('pos:checkout')


# =============================================================================
# Sales List and Detail
# =============================================================================

@login_required
@special_permission_required('can_access_pos')
def sales_list(request):
    """View list of sales - always restricted to user's branch (POS is branch-restricted)."""
    # POS is always branch-restricted - only show sales from user's branch
    branch = request.user.branch
    sales = Sale.objects.filter(branch=branch).exclude(status=Sale.Status.PENDING)

    # Filters (no branch filter since POS is branch-restricted)
    status = request.GET.get('status')
    if status:
        sales = sales.filter(status=status)

    customer_type = request.GET.get('customer_type')
    if customer_type:
        sales = sales.filter(customer_type=customer_type)

    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    if date_from:
        sales = sales.filter(created_at__date__gte=date_from)
    if date_to:
        sales = sales.filter(created_at__date__lte=date_to)

    search = request.GET.get('q')
    if search:
        sales = sales.filter(
            Q(transaction_id__icontains=search) |
            Q(guest_name__icontains=search) |
            Q(customer__first_name__icontains=search) |
            Q(customer__last_name__icontains=search)
        )

    # Calculate totals
    totals = sales.filter(status=Sale.Status.COMPLETED).aggregate(
        total_sales=Sum('total'),
        total_count=Sum('pk')
    )

    paginator = Paginator(sales.order_by('-created_at'), 10)
    page = request.GET.get('page', 1)
    sales = paginator.get_page(page)

    context = {
        'sales': sales,
        'totals': totals,
        'status_choices': Sale.Status.choices,
        'customer_type_choices': Sale.CustomerType.choices,
        'branches': [],  # Empty - POS is always branch-restricted, no dropdown
        'is_branch_restricted': True,
    }
    return render(request, 'pos/sales_list.html', context)


@login_required
@special_permission_required('can_access_pos')
def sale_detail(request, sale_id):
    """View sale details."""
    sale = get_object_or_404(Sale, pk=sale_id, branch=request.user.branch)

    context = {
        'sale': sale,
        'items': sale.items.all(),
        'payments': sale.payments.all(),
        'refunds': sale.refunds.all(),
    }
    return render(request, 'pos/sale_detail.html', context)


@login_required
@special_permission_required('can_access_pos')
def receipt(request, sale_id):
    """Display receipt for printing."""
    sale = get_object_or_404(Sale, pk=sale_id)

    context = {
        'sale': sale,
        'items': sale.items.all(),
        'payments': sale.payments.all(),
    }
    return render(request, 'pos/receipt.html', context)


# =============================================================================
# AJAX Search Endpoints
# =============================================================================

@login_required
@special_permission_required('can_access_pos')
@require_GET
def search_items(request):
    """Search for items (products, medications, services) via AJAX."""
    query = request.GET.get('q', '').strip()
    category = request.GET.get('category', 'all')
    branch = request.user.branch

    results = []

    if not query or len(query) < 2:
        return JsonResponse({'results': []})

    # Search services
    if category in ['all', 'service']:
        services = Service.objects.filter(
            Q(branch=branch) | Q(branch__isnull=True),
            active=True,
            name__icontains=query
        )[:10]
        for s in services:
            results.append({
                'id': s.pk,
                'type': 'SERVICE',
                'name': s.name,
                'category': s.category or 'Service',
                'price': str(s.price),
                'stock': None,
            })

    # Search products from all branches
    if category in ['all', 'product']:
        products = Product.objects.filter(
            item_type='Product',
            name__icontains=query
        ).select_related('branch')[:10]
        for p in products:
            results.append({
                'id': p.pk,
                'type': 'PRODUCT',
                'name': p.name,
                'category': 'Product',
                'price': str(p.price),
                'stock': p.stock_quantity,
            })

    # Search medications from all branches
    if category in ['all', 'medication']:
        medications = Product.objects.filter(
            item_type='Medication',
            name__icontains=query
        ).select_related('branch')[:10]
        for m in medications:
            results.append({
                'id': m.pk,
                'type': 'MEDICATION',
                'name': m.name,
                'category': 'Medication',
                'price': str(m.price),
                'stock': m.stock_quantity,
            })

    return JsonResponse({'results': results})


@login_required
@special_permission_required('can_access_pos')
@require_GET
def search_customers(request):
    """Search for customers via AJAX."""
    query = request.GET.get('q', '').strip()

    if not query or len(query) < 2:
        return JsonResponse({'results': []})

    customers = User.objects.filter(
        is_active=True
    ).filter(
        Q(assigned_role__is_staff_role=False) | Q(assigned_role__isnull=True)
    ).filter(
        Q(first_name__icontains=query) |
        Q(last_name__icontains=query) |
        Q(email__icontains=query)
    )[:10]

    results = []
    for c in customers:
        pets = list(c.pets.filter(is_active=True).values('id', 'name', 'species'))
        results.append({
            'id': c.pk,
            'name': c.get_full_name() or c.email,
            'email': c.email,
            'phone': getattr(c, 'phone_number', ''),
            'pets': pets,
        })

    return JsonResponse({'results': results})


@login_required
@special_permission_required('can_access_pos')
@require_GET
def filter_items_by_branch(request):
    """Filter products and medications by branch via AJAX."""
    branch_id = request.GET.get('branch_id', '').strip()

    results = []

    # Get products from selected branch or all branches
    if branch_id:
        try:
            branch = Branch.objects.get(pk=branch_id)
            products = Product.objects.filter(
                item_type='Product',
                branch=branch,
                is_available=True
            ).select_related('branch')

            medications = Product.objects.filter(
                item_type='Medication',
                branch=branch,
                is_available=True
            ).select_related('branch')
        except Branch.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Branch not found'}, status=404)
    else:
        # All branches
        products = Product.objects.filter(
            item_type='Product',
            is_available=True
        ).select_related('branch')

        medications = Product.objects.filter(
            item_type='Medication',
            is_available=True
        ).select_related('branch')

    # Add products to results
    for p in products.order_by('name'):
        results.append({
            'id': p.pk,
            'type': 'PRODUCT',
            'name': p.name,
            'price': str(p.price),
            'stock': p.stock_quantity,
            'branch_name': p.branch.name if p.branch else 'Unknown',
        })

    # Add medications to results
    for m in medications.order_by('name'):
        results.append({
            'id': m.pk,
            'type': 'MEDICATION',
            'name': m.name,
            'price': str(m.price),
            'stock': m.stock_quantity,
            'branch_name': m.branch.name if m.branch else 'Unknown',
        })

    return JsonResponse({'success': True, 'results': results})


# =============================================================================
# Refunds
# =============================================================================

@login_required
@special_permission_required('can_access_pos')
def refund_request(request, sale_id):
    """
    Request a refund for a sale.
    Supports both full and partial refunds with item selection.
    """
    sale = get_object_or_404(Sale, pk=sale_id, branch=request.user.branch)

    if sale.status not in [Sale.Status.COMPLETED]:
        messages.error(request, 'Only completed sales can be refunded.')
        return redirect('pos:sale_detail', sale_id=sale_id)

    # Get refundable items (items with remaining refundable quantity)
    refundable_items = []
    for item in sale.items.all():
        refundable_qty = item.get_refundable_quantity()
        if refundable_qty > 0:
            refundable_items.append({
                'item': item,
                'refundable_qty': refundable_qty,
                'max_refund_amount': item.unit_price * refundable_qty
            })

    if not refundable_items:
        messages.error(request, 'All items in this sale have already been refunded.')
        return redirect('pos:sale_detail', sale_id=sale_id)

    if request.method == 'POST':
        refund_type = request.POST.get('refund_type', 'FULL')
        reason = request.POST.get('reason', '').strip()
        refund_method = request.POST.get('refund_method', 'CASH')

        if not reason:
            messages.error(request, 'Please provide a reason for the refund.')
            return redirect('pos:refund_request', sale_id=sale_id)

        try:
            if refund_type == 'FULL':
                # Full refund - refund all refundable items
                items_data = [
                    {'sale_item_id': ri['item'].pk, 'quantity': ri['refundable_qty']}
                    for ri in refundable_items
                ]
                refund = Refund.create_partial_refund(
                    sale=sale,
                    items_data=items_data,
                    reason=reason,
                    requested_by=request.user,
                    refund_method=refund_method
                )
                refund.refund_type = Refund.RefundType.FULL
                refund.save(update_fields=['refund_type'])
            else:
                # Partial refund - only selected items
                items_data = []
                for ri in refundable_items:
                    qty_key = f'qty_{ri["item"].pk}'
                    selected_key = f'select_{ri["item"].pk}'

                    if request.POST.get(selected_key):
                        try:
                            qty = int(request.POST.get(qty_key, 0))
                            if qty > 0 and qty <= ri['refundable_qty']:
                                items_data.append({
                                    'sale_item_id': ri['item'].pk,
                                    'quantity': qty
                                })
                        except (ValueError, TypeError):
                            pass

                if not items_data:
                    messages.error(request, 'Please select at least one item to refund.')
                    return redirect('pos:refund_request', sale_id=sale_id)

                refund = Refund.create_partial_refund(
                    sale=sale,
                    items_data=items_data,
                    reason=reason,
                    requested_by=request.user,
                    refund_method=refund_method
                )

            # Auto-approve and complete the refund
            refund.status = Refund.Status.APPROVED
            refund.approved_by = request.user
            refund.save(update_fields=['status', 'approved_by'])

            refund.complete_refund(request.user)
            messages.success(
                request,
                f'Refund {refund.refund_id} completed. ₱{refund.amount} refunded.'
            )

        except ValueError as e:
            messages.error(request, str(e))
            return redirect('pos:refund_request', sale_id=sale_id)

        return redirect('pos:sale_detail', sale_id=sale_id)

    context = {
        'sale': sale,
        'refundable_items': refundable_items,
        'payment_methods': Payment.Method.choices,
        'total_refundable': sum(ri['max_refund_amount'] for ri in refundable_items),
    }
    return render(request, 'pos/refund_request.html', context)


@login_required
@special_permission_required('can_access_pos')
def refund_list(request):
    """View and manage refund requests - always restricted to user's branch."""
    # POS is always branch-restricted - only show refunds from user's branch
    branch = request.user.branch
    refunds = Refund.objects.filter(sale__branch=branch).order_by('-created_at')

    # Filters (no branch filter since POS is branch-restricted)
    status = request.GET.get('status')
    if status:
        refunds = refunds.filter(status=status)

    refund_type = request.GET.get('refund_type')
    if refund_type:
        refunds = refunds.filter(refund_type=refund_type)

    search = request.GET.get('q')
    if search:
        refunds = refunds.filter(
            Q(refund_id__icontains=search) |
            Q(sale__transaction_id__icontains=search) |
            Q(sale__customer__first_name__icontains=search) |
            Q(sale__customer__last_name__icontains=search) |
            Q(sale__guest_name__icontains=search)
        )

    paginator = Paginator(refunds, 10)
    page = request.GET.get('page', 1)
    refunds = paginator.get_page(page)

    context = {
        'refunds': refunds,
        'status_choices': Refund.Status.choices,
        'refund_type_choices': Refund.RefundType.choices,
        'branches': [],  # Empty - POS is always branch-restricted
        'is_branch_restricted': True,
    }
    return render(request, 'pos/refund_list.html', context)


@login_required
@special_permission_required('can_access_pos')
@require_POST
def refund_approve(request, refund_id):
    """Approve a refund request."""
    refund = get_object_or_404(Refund, pk=refund_id)

    if refund.status != Refund.Status.PENDING:
        messages.error(request, 'This refund is not pending.')
        return redirect('pos:refund_list')

    refund.status = Refund.Status.APPROVED
    refund.approved_by = request.user
    refund.save()
    messages.success(request, f'Refund {refund.refund_id} approved.')

    return redirect('pos:refund_list')


@login_required
@special_permission_required('can_access_pos')
@require_POST
def refund_complete(request, refund_id):
    """Complete an approved refund."""
    refund = get_object_or_404(Refund, pk=refund_id)

    try:
        refund.complete_refund(request.user)
        messages.success(request, f'Refund {refund.refund_id} completed.')
    except ValueError as e:
        messages.error(request, str(e))

    return redirect('pos:refund_list')


@login_required
@special_permission_required('can_access_pos')
@require_POST
def refund_reject(request, refund_id):
    """Reject a refund request."""
    refund = get_object_or_404(Refund, pk=refund_id)

    if refund.status != Refund.Status.PENDING:
        messages.error(request, 'This refund is not pending.')
        return redirect('pos:refund_list')

    refund.status = Refund.Status.REJECTED
    refund.notes = request.POST.get('notes', '')
    refund.save()
    messages.info(request, f'Refund {refund.refund_id} rejected.')

    return redirect('pos:refund_list')


# =============================================================================
# Statement of Account from Sale
# =============================================================================

@login_required
@special_permission_required('can_access_pos')
def sale_soa(request, sale_id):
    """
    Generate a Statement of Account from a Sale record.
    Uses the billing app's SOA format for visual consistency.
    """
    import json
    sale = get_object_or_404(Sale, pk=sale_id)

    # Check for custom SOA data first
    soa_data = {}
    if hasattr(sale, 'soa_data') and sale.soa_data:
        try:
            soa_data = json.loads(sale.soa_data)
        except (json.JSONDecodeError, TypeError):
            pass

    # If custom SOA data exists, use it
    if soa_data.get('custom_soa') and 'items' in soa_data:
        # Use custom items and totals
        consultation_items = soa_data['items'].get('consultation_items', [])
        treatment_items = soa_data['items'].get('treatment_items', [])
        boarding_items = soa_data['items'].get('boarding_items', [])
        vaccination_items = soa_data['items'].get('vaccination_items', [])
        surgery_items = soa_data['items'].get('surgery_items', [])
        lab_items = soa_data['items'].get('lab_items', [])
        grooming_items = soa_data['items'].get('grooming_items', [])
        other_items = soa_data['items'].get('other_items', [])
        
        consultation_total = Decimal(soa_data.get('consultation_total', '0'))
        treatment_total = Decimal(soa_data.get('treatment_total', '0'))
        boarding_total = Decimal(soa_data.get('boarding_total', '0'))
        vaccination_total = Decimal(soa_data.get('vaccination_total', '0'))
        surgery_total = Decimal(soa_data.get('surgery_total', '0'))
        lab_total = Decimal(soa_data.get('lab_total', '0'))
        grooming_total = Decimal(soa_data.get('grooming_total', '0'))
        others_total = Decimal(soa_data.get('others_total', '0'))
        total_paid = Decimal(soa_data.get('deposit', '0'))
        
        # Convert dict items to objects for template compatibility
        class ItemObj:
            def __init__(self, data):
                self.name = data['name']
                self.quantity = data['quantity']
                self.unit_price = Decimal(str(data['price']))
                self.line_total = Decimal(str(data['total']))
        
        consultation_items = [ItemObj(item) for item in consultation_items]
        treatment_items = [ItemObj(item) for item in treatment_items]
        boarding_items = [ItemObj(item) for item in boarding_items]
        vaccination_items = [ItemObj(item) for item in vaccination_items]
        surgery_items = [ItemObj(item) for item in surgery_items]
        lab_items = [ItemObj(item) for item in lab_items]
        grooming_items = [ItemObj(item) for item in grooming_items]
        other_items = [ItemObj(item) for item in other_items]
        
        # For template, we need product_items and other_items combined
        product_items = other_items
    else:
        # Build statement data from sale items
        items = list(sale.items.all())

        consultation_items = []
        treatment_items = []
        product_items = []
        other_items = []

        consultation_total = Decimal('0.00')
        treatment_total = Decimal('0.00')
        boarding_total = Decimal('0.00')
        vaccination_total = Decimal('0.00')
        surgery_total = Decimal('0.00')
        lab_total = Decimal('0.00')
        grooming_total = Decimal('0.00')
        others_total = Decimal('0.00')

        for item in items:
            name_lower = item.name.lower()
            
            # Categorize based on name/type
            if item.item_type in ['PRODUCT', 'MEDICATION']:
                product_items.append(item)
                others_total += item.line_total
            elif 'consult' in name_lower or 'fee' in name_lower or 'checkup' in name_lower:
                consultation_items.append(item)
                consultation_total += item.line_total
            elif 'vaccin' in name_lower:
                vaccination_total += item.line_total
            elif 'surgery' in name_lower or 'spay' in name_lower or 'neuter' in name_lower:
                surgery_total += item.line_total
            elif 'lab' in name_lower or 'test' in name_lower or 'exam' in name_lower:
                lab_total += item.line_total
            elif 'groom' in name_lower or 'bath' in name_lower:
                grooming_total += item.line_total
            elif 'board' in name_lower or 'confine' in name_lower or 'admit' in name_lower:
                boarding_total += item.line_total
            elif 'treat' in name_lower or 'medic' in name_lower or 'therapy' in name_lower:
                treatment_items.append(item)
                treatment_total += item.line_total
            else:
                other_items.append(item)
                others_total += item.line_total

        # Get payment info
        payments = sale.payments.filter(status='COMPLETED')
        total_paid = sum(p.amount for p in payments)

    # Customer info
    if sale.customer:
        customer_name = sale.customer.get_full_name() or sale.customer.email
    else:
        customer_name = sale.guest_name or 'Walk-in Customer'

    context = {
        'sale': sale,
        # Individual items per category
        'consultation_items': consultation_items,
        'treatment_items': treatment_items,
        'product_items': product_items,
        'other_items': other_items,
        # Category totals
        'consultation_total': consultation_total,
        'treatment_total': treatment_total,
        'boarding_total': boarding_total,
        'vaccination_total': vaccination_total,
        'surgery_total': surgery_total,
        'lab_total': lab_total,
        'grooming_total': grooming_total,
        'others_total': others_total,
        # Payment info
        'total_paid': total_paid,
        'balance_due': sale.total - total_paid,
        'customer_name': customer_name,
    }

    return render(request, 'pos/sale_soa.html', context)


@login_required
@require_POST
@special_permission_required('can_access_pos')
def send_soa(request, sale_id):
    """
    Manually send Statement of Account notification to registered customer.
    """
    sale = get_object_or_404(Sale, pk=sale_id)
    
    if not sale.customer:
        messages.error(request, 'Cannot send SOA: This sale has no registered customer.')
        return redirect('pos:sale_detail', pk=sale_id)
    
    statement = create_or_release_soa_for_sale(sale)

    if statement:
        messages.success(request, f'Statement of Account sent to {sale.customer.email}')
    else:
        messages.error(request, 'Failed to send Statement of Account. Please try again.')
    
    # Redirect back to referrer or sale detail
    referer = request.META.get('HTTP_REFERER')
    if referer and 'sales' in referer:
        return redirect(referer)
    return redirect('pos:sale_detail', pk=sale_id)


@login_required
@special_permission_required('can_access_pos')
def edit_soa(request, sale_id):
    """
    Edit Statement of Account items and amounts for a Sale.
    Allows adding, editing, and removing individual items per category.
    """
    sale = get_object_or_404(Sale, pk=sale_id)
    
    if request.method == 'POST':
        import json
        
        # Initialize custom SOA items structure
        soa_items = {
            'consultation_items': [],
            'treatment_items': [],
            'boarding_items': [],
            'vaccination_items': [],
            'surgery_items': [],
            'lab_items': [],
            'grooming_items': [],
            'other_items': []
        }
        
        # Process each category
        categories = ['consultation', 'treatment', 'boarding', 'vaccination', 'surgery', 'lab', 'grooming', 'other']
        
        for category in categories:
            # Get item count for this category
            item_count_key = f'{category}_item_count'
            item_count = int(request.POST.get(item_count_key, 0))
            
            for i in range(item_count):
                name = request.POST.get(f'{category}_item_{i}_name', '').strip()
                quantity = request.POST.get(f'{category}_item_{i}_quantity', '1')
                price = request.POST.get(f'{category}_item_{i}_price', '0')
                
                if name:  # Only add items with names
                    try:
                        quantity = int(quantity) if quantity else 1
                        price = float(price) if price else 0
                        total = quantity * price
                        
                        item_data = {
                            'name': name,
                            'quantity': quantity,
                            'price': price,
                            'total': total
                        }
                        
                        soa_items[f'{category}_items'].append(item_data)
                    except (ValueError, TypeError):
                        continue
        
        # Get deposit amount
        deposit = Decimal(request.POST.get('deposit', '0') or '0')
        
        # Calculate totals from items
        consultation_total = sum(item['total'] for item in soa_items['consultation_items'])
        treatment_total = sum(item['total'] for item in soa_items['treatment_items'])
        boarding_total = sum(item['total'] for item in soa_items['boarding_items'])
        vaccination_total = sum(item['total'] for item in soa_items['vaccination_items'])
        surgery_total = sum(item['total'] for item in soa_items['surgery_items'])
        lab_total = sum(item['total'] for item in soa_items['lab_items'])
        grooming_total = sum(item['total'] for item in soa_items['grooming_items'])
        others_total = sum(item['total'] for item in soa_items['other_items'])
        
        # Store complete SOA data
        soa_data = {
            'custom_soa': True,
            'items': soa_items,
            'consultation_total': str(consultation_total),
            'treatment_total': str(treatment_total),
            'boarding_total': str(boarding_total),
            'vaccination_total': str(vaccination_total),
            'surgery_total': str(surgery_total),
            'lab_total': str(lab_total),
            'grooming_total': str(grooming_total),
            'others_total': str(others_total),
            'deposit': str(deposit)
        }
        
        # Save to database
        sale.soa_data = json.dumps(soa_data)
        sale.save(update_fields=['soa_data'])
        
        messages.success(request, 'Statement of Account updated successfully.')
        
        # Auto-send to registered customer
        if sale.customer:
            create_or_release_soa_for_sale(sale)
        
        return redirect('pos:sale_soa', sale_id=sale_id)
    
    # GET request - show edit form with current values
    import json
    soa_data = {}
    if hasattr(sale, 'soa_data') and sale.soa_data:
        try:
            soa_data = json.loads(sale.soa_data)
        except (json.JSONDecodeError, TypeError):
            pass
    
    # Prepare items for editing
    if soa_data.get('custom_soa') and 'items' in soa_data:
        # Load custom items
        consultation_items = soa_data['items'].get('consultation_items', [])
        treatment_items = soa_data['items'].get('treatment_items', [])
        boarding_items = soa_data['items'].get('boarding_items', [])
        vaccination_items = soa_data['items'].get('vaccination_items', [])
        surgery_items = soa_data['items'].get('surgery_items', [])
        lab_items = soa_data['items'].get('lab_items', [])
        grooming_items = soa_data['items'].get('grooming_items', [])
        other_items = soa_data['items'].get('other_items', [])
    else:
        # Build from sale items using categorization logic
        items = list(sale.items.all())
        
        consultation_items = []
        treatment_items = []
        boarding_items = []
        vaccination_items = []
        surgery_items = []
        lab_items = []
        grooming_items = []
        other_items = []
        
        for item in items:
            name_lower = item.name.lower()
            item_data = {
                'name': item.name,
                'quantity': item.quantity,
                'price': float(item.unit_price),
                'total': float(item.line_total)
            }
            
            if item.item_type in ['PRODUCT', 'MEDICATION']:
                other_items.append(item_data)
            elif 'consult' in name_lower or 'fee' in name_lower or 'checkup' in name_lower:
                consultation_items.append(item_data)
            elif 'vaccin' in name_lower:
                vaccination_items.append(item_data)
            elif 'surgery' in name_lower or 'spay' in name_lower or 'neuter' in name_lower:
                surgery_items.append(item_data)
            elif 'lab' in name_lower or 'test' in name_lower or 'exam' in name_lower:
                lab_items.append(item_data)
            elif 'groom' in name_lower or 'bath' in name_lower:
                grooming_items.append(item_data)
            elif 'board' in name_lower or 'confine' in name_lower or 'admit' in name_lower:
                boarding_items.append(item_data)
            elif 'treat' in name_lower or 'medic' in name_lower or 'therapy' in name_lower:
                treatment_items.append(item_data)
            else:
                other_items.append(item_data)
    
    # Get payment info
    payments = sale.payments.filter(status='COMPLETED')
    total_paid = Decimal(soa_data.get('deposit', '0')) or sum(p.amount for p in payments)
    
    # Customer info
    if sale.customer:
        customer_name = sale.customer.get_full_name() or sale.customer.email
    else:
        customer_name = sale.guest_name or 'Walk-in Customer'
    
    context = {
        'sale': sale,
        'customer_name': customer_name,
        'consultation_items': consultation_items,
        'treatment_items': treatment_items,
        'boarding_items': boarding_items,
        'vaccination_items': vaccination_items,
        'surgery_items': surgery_items,
        'lab_items': lab_items,
        'grooming_items': grooming_items,
        'other_items': other_items,
        'total_paid': total_paid,
        'balance_due': sale.total - total_paid,
    }
    
    return render(request, 'pos/edit_soa.html', context)
