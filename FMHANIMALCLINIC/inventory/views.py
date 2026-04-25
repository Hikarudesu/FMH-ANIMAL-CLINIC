"""Views for handling inventory catalog display."""
# pylint: disable=no-member, unused-argument, too-many-lines
from datetime import date, timedelta
from collections import defaultdict
from decimal import Decimal

from django.core.paginator import Paginator
from django.db.models import DecimalField, ExpressionWrapper, F, Q, Sum
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.http import JsonResponse

from accounts.models import User, ActivityLog
from accounts.decorators import module_permission_required
from branches.models import Branch
from notifications.models import Notification
from notifications.email_utils import send_reservation_notification
from notifications.utils import (
    notify_stock_transfer_approved,
    notify_stock_transfer_completed,
    notify_stock_transfer_rejected,
    notify_stock_transfer_requested,
)
from .models import Product, StockAdjustment, Reservation, StockTransfer
from .forms import (
    ProductForm,
    StockAdjustmentForm,
    StockTransferRequestForm,
)


def auto_cancel_expired_reservations():
    """Finds pending reservations older than 24 hours and cancels them."""
    expiration_threshold = timezone.now() - timedelta(hours=24)
    # pylint: disable=no-member
    expired_reservations = Reservation.objects.filter(
        status=Reservation.Status.PENDING,
        created_at__lte=expiration_threshold
    ).select_related('product', 'product__branch', 'user')

    for res in expired_reservations:
        res.status = Reservation.Status.CANCELLED
        res.save()

        # Restore stock (using ADD since we're restocking cancelled items)
        StockAdjustment.objects.create(
            branch=res.product.branch,
            product=res.product,
            adjustment_type='ADD',
            reference=f"RSV-{res.pk}-AUTO-EXP",
            date=timezone.now().date(),
            quantity=res.quantity,
            cost_per_unit=res.product.unit_cost,
            reason="Automatically cancelled due to 24-hour expiration.",
        )

        # Notify admins (hierarchy level >= 8: Branch Admin or higher)
        admin_users = User.objects.filter(
            assigned_role__hierarchy_level__gte=8
        )
        for admin in admin_users:
            Notification.objects.create(
                user=admin,
                title="Reservation Auto-Cancelled",
                message=(
                    f"Reservation #{res.pk} for {res.quantity}x {res.product.name} "
                    f"reserved by {res.user.get_full_name() or res.user.username} "
                    f"was automatically cancelled (24h expired)."
                ),
                notification_type=Notification.NotificationType.PRODUCT_RESERVATION,
                module_context=Notification.ModuleContext.INVENTORY,
                related_object_id=res.pk,
            )

        # Notify user
        Notification.objects.create(
            user=res.user,
            title="Reservation Expired",
            message=(
                f"Your reservation for {res.quantity}x {res.product.name} "
                f"has expired after 24 hours and was cancelled."
            ),
            notification_type=Notification.NotificationType.PRODUCT_RESERVATION,
            module_context=Notification.ModuleContext.INVENTORY,
            related_object_id=res.pk,
        )


@login_required
def catalog_view(request):
    """Digital Catalog displaying products available."""
    auto_cancel_expired_reservations()

    # pylint: disable=no-member
    branches = Branch.objects.filter(is_active=True)
    products = Product.objects.exclude(
        item_type='Medication').select_related('branch')

    selected_branch_id = request.GET.get('branch')

    if selected_branch_id:
        try:
            products = products.filter(branch_id=selected_branch_id)
            selected_branch = Branch.objects.get(  # pylint: disable=no-member
                id=selected_branch_id
            )
        except Branch.DoesNotExist:  # pylint: disable=no-member
            selected_branch = None
    else:
        selected_branch = None

    # User's own reservations
    user_reservations = Reservation.objects.filter(  # pylint: disable=no-member
        user=request.user
    ).select_related('product', 'product__branch')

    # Pagination for products
    page_number = request.GET.get('page', 1)
    paginator = Paginator(products, 12)
    page_obj = paginator.get_page(page_number)

    return render(request, 'inventory/catalog.html', {
        'products': page_obj,
        'page_obj': page_obj,
        'branches': branches,
        'selected_branch': selected_branch,
        'user_reservations': user_reservations,
    })


@login_required
@module_permission_required('inventory', 'VIEW')
def inventory_management_view(request):
    """Admin view for managing stock adjustments."""
    auto_cancel_expired_reservations()

    # Check if user is branch-restricted
    is_branch_restricted = request.user.is_module_branch_restricted(
        'inventory')
    user_branch = getattr(request.user, 'branch', None)

    # pylint: disable=no-member
    adjustments = StockAdjustment.objects.all().select_related(
        'product', 'branch')

    branches = Branch.objects.filter(is_active=True)
    selected_branch_id = request.GET.get('branch')
    selected_status = request.GET.get('status', '')
    selected_type = request.GET.get('type', '')
    search_query = request.GET.get('q', '').strip()
    products = Product.objects.all().select_related('branch')

    # Apply branch restriction first if user is restricted
    if is_branch_restricted and user_branch:
        adjustments = adjustments.filter(branch=user_branch)
        products = products.filter(branch=user_branch)
        selected_branch_id = str(user_branch.id)
    elif selected_branch_id:
        adjustments = adjustments.filter(branch_id=selected_branch_id)
        products = products.filter(branch_id=selected_branch_id)

    # Apply type filter
    if selected_type:
        products = products.filter(item_type=selected_type)

    # Apply search filter
    if search_query:
        products = products.filter(
            Q(name__icontains=search_query) |
            Q(sku__icontains=search_query) |
            Q(description__icontains=search_query)
        )

    # Apply status filter
    if selected_status:
        filtered_products = []
        for p in products:
            if p.status == selected_status:
                filtered_products.append(p)
        products = filtered_products
    else:
        products = list(products)

    # Health Metrics
    total_value = sum(p.inventory_value for p in products)
    low_stock_count = sum(1 for p in products if p.status == 'Low Stock')
    out_of_stock_count = sum(
        1 for p in products if p.status == 'Out of Stock'
    )

    # Pending reservations for admin view
    # pylint: disable=no-member
    pending_reservations = Reservation.objects.filter(
        status=Reservation.Status.PENDING
    ).select_related('product', 'user')

    if is_branch_restricted and user_branch:
        pending_reservations = pending_reservations.filter(
            product__branch=user_branch
        )
    elif selected_branch_id:
        pending_reservations = pending_reservations.filter(
            product__branch_id=selected_branch_id
        )

    # Build filter list for filter_bar component
    status_filters = [
        {
            'name': 'type',
            'icon': 'bx-box',
            'default_label': 'All Types',
            'has_value': bool(selected_type),
            'selected_label': selected_type,
            'options': [
                {'value': 'Product', 'label': 'Products',
                    'selected': selected_type == 'Product'},
                {'value': 'Medication', 'label': 'Medications',
                    'selected': selected_type == 'Medication'},
                {'value': 'Accessories', 'label': 'Accessories',
                    'selected': selected_type == 'Accessories'},
            ]
        },
        {
            'name': 'status',
            'icon': 'bx-pulse',
            'default_label': 'All Status',
            'has_value': bool(selected_status),
            'selected_label': selected_status,
            'options': [
                {'value': 'In Stock', 'label': 'In Stock',
                    'selected': selected_status == 'In Stock'},
                {'value': 'Low Stock', 'label': 'Low Stock',
                    'selected': selected_status == 'Low Stock'},
                {'value': 'Out of Stock', 'label': 'Out of Stock',
                    'selected': selected_status == 'Out of Stock'},
            ]
        },
    ]

    # Only add branch filter if user is NOT branch-restricted
    if not is_branch_restricted:
        status_filters.append({
            'name': 'branch',
            'icon': 'bx-building-house',
            'default_label': 'All Branches',
            'has_value': bool(selected_branch_id),
            'selected_label': '',
            'options': []
        })
        # Populate branch filter options
        for branch in branches:
            is_selected = str(branch.id) == str(
                selected_branch_id) if selected_branch_id else False
            status_filters[-1]['options'].append({
                'value': branch.id,
                'label': branch.name,
                'selected': is_selected
            })
            if is_selected:
                status_filters[-1]['selected_label'] = branch.name

    show_clear = bool(search_query or selected_type or selected_status or (
        selected_branch_id and not is_branch_restricted))

    # Check permissions for CRUD buttons
    can_create = request.user.has_module_permission('inventory', 'CREATE')
    can_edit = request.user.has_module_permission('inventory', 'EDIT')
    can_delete = request.user.is_admin_role() or request.user.has_module_permission('inventory', 'DELETE')

    # Pagination for 20 items per page across all 3 lists
    page_number = request.GET.get('page', 1)
    
    paginator_products = Paginator(products, 20)
    page_products = paginator_products.get_page(page_number)
    
    paginator_adjustments = Paginator(adjustments, 20)
    page_adjustments = paginator_adjustments.get_page(page_number)
    
    paginator_reservations = Paginator(pending_reservations, 20)
    page_reservations = paginator_reservations.get_page(page_number)

    return render(request, 'inventory/management.html', {
        'adjustments': page_adjustments,
        'products': page_products,
        'branches': [] if is_branch_restricted else branches,
        'selected_branch_id': selected_branch_id,
        'selected_status': selected_status,
        'selected_type': selected_type,
        'search_value': search_query,
        'status_filters': status_filters,
        'show_clear': show_clear,
        'total_value': total_value,
        'low_stock_count': low_stock_count,
        'out_of_stock_count': out_of_stock_count,
        'pending_reservations': page_reservations,
        'can_create': can_create,
        'can_edit': can_edit,
        'can_delete': can_delete,
        'is_branch_restricted': is_branch_restricted,
    })


@login_required
@module_permission_required('inventory', 'CREATE')
def product_create_view(request):
    """View to create a new inventory item."""
    if request.method == 'POST':
        form = ProductForm(request.POST)
        if form.is_valid():
            product = form.save()

            # Create initial stock adjustment if stock_quantity > 0
            if product.stock_quantity > 0:
                StockAdjustment.objects.create(
                    branch=product.branch,
                    product=product,
                    adjustment_type='ADD',
                    reference=f"NEW-ITEM-{product.pk}",
                    date=timezone.now().date(),
                    quantity=product.stock_quantity,
                    cost_per_unit=product.unit_cost,
                    reason=f"Initial stock for new item: {product.name}",
                )

            messages.success(request, "Item created successfully.")
            return redirect('inventory:management')
    else:
        form = ProductForm()

    return render(request, 'inventory/product_form.html', {'form': form})


@login_required
@module_permission_required('inventory', 'EDIT')
def product_edit_view(request, pk):
    """View to edit an existing inventory item."""
    product = get_object_or_404(Product, pk=pk)

    if request.method == 'POST':
        form = ProductForm(request.POST, instance=product)
        if form.is_valid():
            form.save()
            messages.success(request, "Item updated successfully.")
            return redirect('inventory:management')
    else:
        form = ProductForm(instance=product)

    return render(request, 'inventory/product_form.html', {
        'form': form, 'product': product
    })


@login_required
def product_delete_view(request, pk):
    """Soft-delete an inventory item.

    Superadmin-role users can always delete. Other roles require inventory DELETE permission.
    """
    can_delete = request.user.is_admin_role() or request.user.has_module_permission('inventory', 'DELETE')
    if not can_delete:
        messages.warning(request, 'You do not have DELETE permission for inventory.')
        return redirect('inventory:management')

    if request.method != 'POST':
        messages.warning(request, 'Invalid request method.')
        return redirect('inventory:management')

    product = get_object_or_404(Product, pk=pk)
    product_name = product.name
    product.delete()  # Soft delete via SoftDeleteModel
    messages.success(request, f'Item "{product_name}" deleted successfully.')
    return redirect('inventory:management')


@login_required
@module_permission_required('inventory', 'CREATE')
def stock_adjustment_create_view(request):
    """Admin view to create a new stock adjustment."""
    if request.method == 'POST':
        form = StockAdjustmentForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(
                request, "Stock adjustment recorded successfully.")
            return redirect('inventory:management')
        else:
            messages.error(
                request,
                "Failed to record adjustment. Please check the form errors."
            )
    else:
        form = StockAdjustmentForm()

    return render(request, 'inventory/adjustment_form.html', {
        'form': form
    })


@login_required
def reserve_product_view(request, pk):
    """Handle a product reservation from the digital catalog."""
    product = get_object_or_404(Product, pk=pk)

    if request.method != 'POST':
        return redirect('inventory:catalog')

    try:
        quantity = int(request.POST.get('quantity', 1))
    except (ValueError, TypeError):
        messages.error(request, "Invalid quantity.")
        return redirect('inventory:catalog')

    pickup_date_str = request.POST.get('pickup_date')

    # Validate stock
    if quantity < 1:
        messages.error(request, "Quantity must be at least 1.")
        return redirect('inventory:catalog')

    if quantity > product.stock_quantity:
        messages.error(
            request,
            f"Not enough stock. Only {product.stock_quantity} available."
        )
        return redirect('inventory:catalog')

    # Create reservation
    reservation = Reservation.objects.create(  # pylint: disable=no-member
        user=request.user,
        product=product,
        quantity=quantity,
        pickup_date=pickup_date_str if pickup_date_str else None,
        notes=request.POST.get('notes', ''),
    )

    # Log stock adjustment (REMOVE for reservation)
    StockAdjustment.objects.create(  # pylint: disable=no-member
        branch=product.branch,
        product=product,
        adjustment_type='REMOVE',
        reference=f"RSV-{reservation.pk}",
        date=date.today(),
        quantity=quantity,  # save() enforces negative sign
        cost_per_unit=product.unit_cost,
        reason=f"Reserved by {request.user.get_full_name() or request.user.username}",
    )

    # Notify all admin users (hierarchy level >= 8: Branch Admin or higher)
    admin_users = User.objects.filter(  # pylint: disable=no-member
        assigned_role__hierarchy_level__gte=8
    )
    for admin in admin_users:
        Notification.objects.create(  # pylint: disable=no-member
            user=admin,
            title="New Product Reservation",
            message=(
                f"{request.user.get_full_name() or request.user.username} "
                f"reserved {quantity}x {product.name}."
            ),
            notification_type=Notification.NotificationType.PRODUCT_RESERVATION,
            module_context=Notification.ModuleContext.INVENTORY,
            related_object_id=reservation.pk,
        )

    # Email notification to user
    send_reservation_notification(reservation)

    return redirect('inventory:reservation_success', pk=reservation.pk)


@login_required
def reservation_success_view(request, pk):
    """Confirmation page after a successful reservation."""
    reservation = get_object_or_404(
        Reservation, pk=pk, user=request.user
    )
    return render(request, 'inventory/reservation_success.html', {
        'reservation': reservation,
    })


@login_required
def my_reservations_view(request):
    """User view for their reservation history."""
    auto_cancel_expired_reservations()
    # pylint: disable=no-member
    reservations = Reservation.objects.filter(
        user=request.user
    ).select_related('product', 'product__branch')

    return render(request, 'inventory/my_reservations.html', {
        'reservations': reservations,
    })


@login_required
@module_permission_required('inventory', 'EDIT')
def confirm_reservation_view(request, pk):
    """Admin confirms a reservation when the user arrives to pick up."""
    reservation = get_object_or_404(Reservation, pk=pk)

    if reservation.status != Reservation.Status.PENDING:
        messages.warning(request, "This reservation is no longer pending.")
        return redirect('inventory:management')

    reservation.status = Reservation.Status.RELEASED
    reservation.save()

    # Notify the user
    Notification.objects.create(  # pylint: disable=no-member
        user=reservation.user,
        title="Reservation Released",
        message=(
            f"Your reservation for {reservation.quantity}x "
            f"{reservation.product.name} has been released. "
            f"Thank you for your purchase!"
        ),
        notification_type=Notification.NotificationType.PRODUCT_RESERVATION,
        module_context=Notification.ModuleContext.INVENTORY,
        related_object_id=reservation.pk,
    )

    # Email notification
    send_reservation_notification(reservation)

    messages.success(
        request,
        f"Reservation RSV-{reservation.pk} released."
    )
    return redirect('inventory:management')


@login_required
@module_permission_required('inventory', 'DELETE')
def cancel_reservation_view(request, pk):
    """Admin cancels a reservation. Stock is restored."""
    reservation = get_object_or_404(
        Reservation, pk=pk
    )

    if reservation.status != Reservation.Status.PENDING:
        messages.warning(request, "This reservation cannot be cancelled.")
        return redirect('inventory:management')

    reservation.status = Reservation.Status.CANCELLED
    reservation.save()

    # Restore stock via ADD adjustment
    StockAdjustment.objects.create(  # pylint: disable=no-member
        branch=reservation.product.branch,
        product=reservation.product,
        adjustment_type='ADD',
        reference=f"RSV-{reservation.pk}-CANCEL",
        date=date.today(),
        quantity=reservation.quantity,  # positive = stock added back
        cost_per_unit=reservation.product.unit_cost,
        reason=f"Reservation cancelled by {request.user.get_full_name() or request.user.username}",
    )

    # Notify admins (hierarchy level >= 8: Branch Admin or higher)
    admin_users = User.objects.filter(  # pylint: disable=no-member
        assigned_role__hierarchy_level__gte=8
    )
    for admin in admin_users:
        Notification.objects.create(  # pylint: disable=no-member
            user=admin,
            title="Reservation Cancelled",
            message=(
                f"Reservation for {reservation.quantity}x "
                f"{reservation.product.name} by "
                f"{reservation.user.get_full_name() or reservation.user.username} "
                f"was cancelled. Stock has been restored."
            ),
            notification_type=Notification.NotificationType.PRODUCT_RESERVATION,
            module_context=Notification.ModuleContext.INVENTORY,
            related_object_id=reservation.pk,
        )

    # Notify user it was cancelled by the clinic
    Notification.objects.create(  # pylint: disable=no-member
        user=reservation.user,
        title="Reservation Cancelled",
        message=(
            f"Your reservation for {reservation.quantity}x {reservation.product.name} "
            f"was cancelled by the clinic."
        ),
        notification_type=Notification.NotificationType.PRODUCT_RESERVATION,
        module_context=Notification.ModuleContext.INVENTORY,
        related_object_id=reservation.pk,
    )

    # Email notification
    send_reservation_notification(reservation)

    messages.success(
        request, "Reservation cancelled. Stock has been restored.")
    return redirect('inventory:management')


@login_required
def stock_transfer_list_view(request):
    """List all stock transfers for the user's branch with filtering and search."""
    is_admin_user = request.user.is_admin_role()
    can_view_transfer_list = (
        request.user.has_module_permission('stock_transfers', 'VIEW')
        or request.user.has_special_permission('can_request_stock_transfer')
    )
    if not can_view_transfer_list:
        messages.warning(
            request,
            'You do not have view permission for stock transfers.'
        )
        return redirect('admin_dashboard')

    search_query = request.GET.get('q', '').strip()
    selected_status = request.GET.get('status', '')
    selected_branch_id = request.GET.get('branch_id', '')

    is_special_request_only_user = (
        request.user.has_special_permission('can_request_stock_transfer')
        and not request.user.has_module_permission('stock_transfers', 'VIEW')
    )

    if is_special_request_only_user:
        transfers = StockTransfer.objects.filter(  # pylint: disable=no-member
            requested_by=request.user
        ).select_related(
            'source_product', 'source_product__branch',
            'destination_branch', 'requested_by', 'processed_by'
        )
    elif (
        not is_admin_user
        and hasattr(request.user, 'staff_profile')
        and request.user.staff_profile.branch
    ):
        branch = request.user.staff_profile.branch
        transfers = StockTransfer.objects.filter(  # pylint: disable=no-member
            Q(source_product__branch=branch) | Q(destination_branch=branch)
        ).select_related(
            'source_product', 'source_product__branch',
            'destination_branch', 'requested_by', 'processed_by'
        )
    else:
        # Admin or HQ staff sees all
        transfers = StockTransfer.objects.all().select_related(  # pylint: disable=no-member
            'source_product', 'source_product__branch',
            'destination_branch', 'requested_by', 'processed_by'
        )

    # Apply search filter (only on field lookups, no method calls)
    if search_query:
        transfers = transfers.filter(
            Q(source_product__name__icontains=search_query) |
            Q(destination_branch__name__icontains=search_query) |
            Q(requested_by__isnull=False, requested_by__username__icontains=search_query) |
            Q(requested_by__isnull=False, requested_by__first_name__icontains=search_query) |
            Q(requested_by__isnull=False,
              requested_by__last_name__icontains=search_query)
        ).distinct()

    # Apply status filter
    if selected_status:
        transfers = transfers.filter(status=selected_status)

    # Apply branch filter (not relevant for request-only users viewing own requests)
    if selected_branch_id and not is_special_request_only_user:
        transfers = transfers.filter(
            Q(source_product__branch_id=selected_branch_id) |
            Q(destination_branch_id=selected_branch_id)
        )

    # Get branches for filter dropdown
    branches = Branch.objects.filter(is_active=True)

    # Build filter list for filter_bar component
    status_filters = [
        {
            'name': 'status',
            'icon': 'bx-pulse',
            'default_label': 'All Status',
            'has_value': bool(selected_status),
            'selected_label': selected_status,
            'options': [
                {'value': 'Pending', 'label': 'Pending',
                    'selected': selected_status == 'Pending'},
                {'value': 'Approved', 'label': 'Approved',
                    'selected': selected_status == 'Approved'},
                {'value': 'Rejected', 'label': 'Rejected',
                    'selected': selected_status == 'Rejected'},
                {'value': 'Completed', 'label': 'Completed',
                    'selected': selected_status == 'Completed'},
            ]
        },
        {
            'name': 'branch_id',
            'icon': 'bx-building-house',
            'default_label': 'All Branches',
            'has_value': bool(selected_branch_id),
            'selected_label': '',
            'options': []
        }
    ]

    # Populate branch filter options
    for branch in branches:
        is_selected = str(branch.id) == str(
            selected_branch_id) if selected_branch_id else False
        status_filters[1]['options'].append({
            'value': branch.id,
            'label': branch.name,
            'selected': is_selected
        })
        if is_selected:
            status_filters[1]['selected_label'] = branch.name

    show_clear = bool(selected_status or (selected_branch_id and not is_special_request_only_user))
    
    paginator = Paginator(transfers, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'transfers': page_obj,
        'page_obj': page_obj,
        'page_title': 'Stock Transfers',
        'search_value': search_query,
        'selected_status': selected_status,
        'status_filters': status_filters,
        'show_clear': show_clear,
        'is_special_request_only_user': is_special_request_only_user,
        'is_admin_user': is_admin_user,
    }
    return render(request, 'inventory/stock_transfer_list.html', context)


@login_required
def stock_transfer_request_view(request):
    """View to request stock from another branch."""
    can_create_transfer_request = (
        request.user.has_module_permission('stock_transfers', 'CREATE')
        or request.user.has_special_permission('can_request_stock_transfer')
    )
    if not can_create_transfer_request:
        messages.warning(
            request,
            'You do not have create permission for stock transfer requests.'
        )
        return redirect('admin_dashboard')

    if not hasattr(request.user, 'staff_profile') or not request.user.staff_profile.branch:
        messages.error(
            request, "You must be assigned to a branch to request transfers.")
        return redirect('inventory:management')

    # Prevent admin users from creating transfer requests
    # They can only approve requests made by other branches
    if (hasattr(request.user, 'assigned_role') and
        request.user.assigned_role and
            request.user.assigned_role.hierarchy_level >= 10):
        messages.warning(
            request,
            "Admin users cannot create transfer requests. You can only approve transfer requests made by other branches."
        )
        return redirect('inventory:transfer_list')

    branch = request.user.staff_profile.branch

    if request.method == 'POST':
        form = StockTransferRequestForm(request.POST, user_branch=branch)
        if form.is_valid():
            transfer = form.save(commit=False)
            transfer.requested_by = request.user
            transfer.save()
            notify_stock_transfer_requested(transfer)
            messages.success(
                request,
                f"Requested {transfer.quantity}x {transfer.source_product.name} "
                f"from {transfer.source_product.branch.name}."
            )
            return redirect('inventory:transfer_list')
    else:
        form = StockTransferRequestForm(user_branch=branch)

    context = {
        'form': form,
        'page_title': 'Request Stock Transfer',
        'branch': branch
    }
    return render(request, 'inventory/stock_transfer_form.html', context)


@login_required
def stock_transfer_update_status_view(request, pk):
    """Update status of a stock transfer (Approve, Reject, Complete)."""
    can_manage_transfers = (
        request.user.is_admin_role()
        or request.user.has_module_permission('stock_transfers', 'MANAGE')
    )
    if not can_manage_transfers:
        messages.warning(
            request,
            'You do not have manage permission for stock transfers.'
        )
        return redirect('admin_dashboard')

    transfer = get_object_or_404(StockTransfer, pk=pk)

    if request.method == 'POST':
        action = request.POST.get('action')

        try:
            if action == 'approve':
                # Backend validation: Only allow approval of Pending transfers
                if transfer.status != StockTransfer.Status.PENDING:
                    messages.error(
                        request,
                        f"Transfer #{transfer.pk} cannot be approved - "
                        f"current status is '{transfer.status}'."
                    )
                    return redirect('inventory:transfer_list')

                transfer.status = StockTransfer.Status.APPROVED
                transfer.processed_by = request.user
                transfer.save()
                notify_stock_transfer_approved(transfer, request.user)
                messages.success(request, f"Transfer #{transfer.pk} approved.")

            elif action == 'reject':
                # Backend validation: Only allow rejection of Pending transfers
                if transfer.status != StockTransfer.Status.PENDING:
                    messages.error(
                        request,
                        f"Transfer #{transfer.pk} cannot be rejected - "
                        f"current status is '{transfer.status}'."
                    )
                    return redirect('inventory:transfer_list')

                transfer.status = StockTransfer.Status.REJECTED
                transfer.processed_by = request.user
                transfer.save()
                notify_stock_transfer_rejected(transfer, request.user)
                messages.success(request, f"Transfer #{transfer.pk} rejected.")

            elif action == 'complete':
                # Backend validation: Only allow completion of Approved transfers
                if transfer.status != StockTransfer.Status.APPROVED:
                    messages.error(
                        request,
                        f"Transfer #{transfer.pk} cannot be completed - "
                        f"current status is '{transfer.status}'."
                    )
                    return redirect('inventory:transfer_list')

                transfer.complete_transfer(request.user)
                notify_stock_transfer_completed(transfer, request.user)
                messages.success(
                    request, f"Transfer #{transfer.pk} completed successfully.")
        except ValueError as e:
            messages.error(request, str(e))

    return redirect('inventory:transfer_list')


@login_required
def super_admin_stock_view(request):
    """
    Stock Level Monitor.
    Displays Low Stock alerts using min_stock_level threshold.
    Superadmin can view all branches.
    Non-superadmin users are restricted to their own branch.
    """
    can_view_stock_monitor = (
        request.user.has_module_permission('stock_monitor', 'VIEW')
        or request.user.has_special_permission('can_access_stock_monitor')
    )
    if not can_view_stock_monitor:
        messages.warning(
            request, 'You do not have VIEW permission for this section.')
        return redirect('admin_dashboard')

    # Stock Monitor rule:
    # - Superadmin can see all branches
    # - Any non-superadmin user is restricted to their own branch
    #   (this view is special-permission based, not module-permission based)
    is_branch_restricted = not request.user.is_superuser

    user_branch = request.user.branch
    selected_branch = None
    selected_branch_id = request.GET.get('branch_id', '').strip()
    selected_status = request.GET.get('status', '')
    search_query = request.GET.get('q', '').strip()

    branches = Branch.objects.filter(is_active=True).order_by('name')

    # Base queryset
    products = Product.objects.filter(
        is_deleted=False,
    ).select_related('branch')

    # Apply branch visibility rule
    if is_branch_restricted:
        if user_branch:
            products = products.filter(branch=user_branch)
            selected_branch = user_branch
        else:
            products = products.none()
    elif selected_branch_id:
        selected_branch = branches.filter(id=selected_branch_id).first()
        if selected_branch:
            products = products.filter(branch=selected_branch)

    # Apply search filter
    if search_query:
        products = products.filter(
            Q(name__icontains=search_query) |
            Q(sku__icontains=search_query)
        )

    # Low Stock: current quantity <= min_stock_level
    low_stock = products.filter(
        stock_quantity__lte=F('min_stock_level')
    ).exclude(
        stock_quantity=0  # Exclude out of stock to show separately
    ).order_by('stock_quantity')

    # Out of Stock: quantity = 0
    out_of_stock = products.filter(stock_quantity=0).order_by('name')

    # Apply status filter
    if selected_status == 'Low Stock':
        low_stock_list = list(low_stock)
        out_of_stock_list = []
    elif selected_status == 'Out of Stock':
        low_stock_list = []
        out_of_stock_list = list(out_of_stock)
    elif selected_status == 'In Stock':
        low_stock_list = []
        out_of_stock_list = []
    else:
        low_stock_list = list(low_stock)
        out_of_stock_list = list(out_of_stock)

    # Calculate stats
    low_stock_count = low_stock.count()
    out_of_stock_count = out_of_stock.count()
    total_critical = low_stock_count + out_of_stock_count

    # Total products and inventory value (current visible scope)
    total_products = products.count()
    cost_value_expr = ExpressionWrapper(
        F('stock_quantity') * F('unit_cost'),
        output_field=DecimalField(max_digits=18, decimal_places=2),
    )
    retail_value_expr = ExpressionWrapper(
        F('stock_quantity') * F('price'),
        output_field=DecimalField(max_digits=18, decimal_places=2),
    )
    total_inventory_value = products.aggregate(v=Sum(cost_value_expr))['v'] or Decimal('0.00')
    total_inventory_value_estimated = products.aggregate(v=Sum(retail_value_expr))['v'] or Decimal('0.00')

    # If all visible products have zero unit_cost, show an estimate from retail price.
    missing_cost_count = products.filter(unit_cost=0).count()
    has_products = total_products > 0
    all_costs_missing = has_products and missing_cost_count == total_products

    # Branch breakdown for visible scope
    branch_breakdown = {}
    if is_branch_restricted and selected_branch:
        branch_inventory_value = products.aggregate(v=Sum(cost_value_expr))['v'] or Decimal('0.00')
        branch_inventory_estimated = products.aggregate(v=Sum(retail_value_expr))['v'] or Decimal('0.00')
        branch_breakdown[selected_branch.id] = {
            'name': selected_branch.name,
            'low': low_stock.count(),
            'out': out_of_stock.count(),
            'total': low_stock.count() + out_of_stock.count(),
            'product_count': total_products,
            'inventory_value': branch_inventory_value,
            'inventory_value_estimated': branch_inventory_estimated,
            'all_costs_missing': all_costs_missing,
        }
    elif not is_branch_restricted:
        visible_branch_ids = products.values_list(
            'branch_id', flat=True).distinct()
        for branch in branches.filter(id__in=visible_branch_ids):
            branch_products = products.filter(branch=branch)
            branch_low = branch_products.filter(
                stock_quantity__lte=F('min_stock_level')
            ).exclude(stock_quantity=0).count()
            branch_out = branch_products.filter(stock_quantity=0).count()
            branch_product_count = branch_products.count()
            branch_missing_cost_count = branch_products.filter(unit_cost=0).count()
            branch_all_costs_missing = (
                branch_product_count > 0
                and branch_missing_cost_count == branch_product_count
            )
            branch_inventory_value = branch_products.aggregate(v=Sum(cost_value_expr))['v'] or Decimal('0.00')
            branch_inventory_estimated = branch_products.aggregate(v=Sum(retail_value_expr))['v'] or Decimal('0.00')
            branch_breakdown[branch.id] = {
                'name': branch.name,
                'low': branch_low,
                'out': branch_out,
                'total': branch_low + branch_out,
                'product_count': branch_product_count,
                'inventory_value': branch_inventory_value,
                'inventory_value_estimated': branch_inventory_estimated,
                'all_costs_missing': branch_all_costs_missing,
            }

    # Build filter list for filter_bar component (no branch filter - branch restricted)
    status_filters = [
        {
            'name': 'status',
            'icon': 'bx-pulse',
            'default_label': 'All Status',
            'has_value': bool(selected_status),
            'selected_label': selected_status,
            'options': [
                {'value': 'In Stock', 'label': 'In Stock',
                    'selected': selected_status == 'In Stock'},
                {'value': 'Low Stock', 'label': 'Low Stock',
                    'selected': selected_status == 'Low Stock'},
                {'value': 'Out of Stock', 'label': 'Out of Stock',
                    'selected': selected_status == 'Out of Stock'},
            ]
        }
    ]

    show_clear = bool(search_query or selected_status)

    return render(request, 'inventory/stock_level_monitor.html', {
        'branches': [] if is_branch_restricted else branches,
        'selected_branch': selected_branch,
        'low_stock': low_stock_list,
        'out_of_stock': out_of_stock_list,
        'low_stock_count': low_stock_count,
        'out_of_stock_count': out_of_stock_count,
        'total_critical': total_critical,
        'total_products': total_products,
        'total_inventory_value': total_inventory_value,
        'total_inventory_value_estimated': total_inventory_value_estimated,
        'all_costs_missing': all_costs_missing,
        'missing_cost_count': missing_cost_count,
        'branch_breakdown': branch_breakdown,
        'page_title': 'Stock Level Monitor',
        'search_value': search_query,
        'selected_status': selected_status,
        'status_filters': status_filters,
        'show_clear': show_clear,
        'is_branch_restricted': is_branch_restricted,
    })


def group_logs_by_date(logs):
    """
    Groups logs into date categories: Today, Yesterday, This Week, This Month, Older.
    Excludes overlapping entries - each log appears in only its most specific category.
    """
    now = timezone.now()
    today = now.date()
    yesterday = today - timedelta(days=1)
    week_start = today - timedelta(days=today.weekday())
    month_start = today.replace(day=1)

    # Use ordered dict-like structure for clean grouping
    groups = {
        'Today': [],
        'Yesterday': [],
        'This Week': [],
        'This Month': [],
        'Older': []
    }

    for log in logs:
        log_date = log.timestamp.date() if log.timestamp else None
        if not log_date:
            continue

        # Mutually exclusive categorization (most specific first)
        if log_date == today:
            groups['Today'].append(log)
        elif log_date == yesterday:
            groups['Yesterday'].append(log)
        elif log_date >= week_start and log_date > yesterday:
            # This Week excludes Today and Yesterday
            groups['This Week'].append(log)
        elif log_date >= month_start and log_date < week_start:
            # This Month excludes This Week
            groups['This Month'].append(log)
        else:
            groups['Older'].append(log)

    # Sort each group by timestamp descending
    for key in groups:
        groups[key].sort(key=lambda x: x.timestamp, reverse=True)

    # Return only non-empty groups in order
    return [(name, logs) for name, logs in groups.items() if logs]


def group_logs_by_branch(logs):
    """Groups logs by branch."""
    grouped = defaultdict(list)
    for log in logs:
        branch_name = log.branch.name if log.branch else 'System-wide'
        grouped[branch_name].append(log)

    # Sort each group by timestamp descending
    for key in grouped:
        grouped[key].sort(key=lambda x: x.timestamp, reverse=True)

    return sorted(grouped.items(), key=lambda x: x[0])


@login_required
@module_permission_required('activity_logs', 'VIEW')
def activity_logs_view(request):
    """
    Comprehensive Activity Log with filtering by Date, Branch, and Category.
    """
    # Get all logs
    logs = ActivityLog.objects.select_related(
        'user', 'branch').all().order_by('-timestamp')

    # Filter by branch
    branch_id = request.GET.get('branch_id')
    if branch_id:
        if branch_id == 'system':
            logs = logs.filter(branch__isnull=True)
        else:
            logs = logs.filter(branch_id=branch_id)

    # Filter by category
    category = request.GET.get('category')
    if category and category != 'all':
        logs = logs.filter(category=category)

    # Filter by date range (for grouping preference)
    date_filter = request.GET.get('date_filter', 'all')
    now = timezone.now()
    today = now.date()

    if date_filter == 'today':
        logs = logs.filter(timestamp__date=today)
    elif date_filter == 'yesterday':
        yesterday = today - timedelta(days=1)
        logs = logs.filter(timestamp__date=yesterday)
    elif date_filter == 'week':
        week_start = today - timedelta(days=today.weekday())
        logs = logs.filter(timestamp__date__gte=week_start)
    elif date_filter == 'month':
        month_start = today.replace(day=1)
        logs = logs.filter(timestamp__date__gte=month_start)

    # Determine grouping preference via GET parameter
    group_by = request.GET.get('group_by', 'date')

    context = {
        'logs': logs,
        'page_title': 'System Activity Logs',
        'branches': Branch.objects.filter(is_active=True),
        'categories': ActivityLog.Category.choices,
        'group_by': group_by,
        'selected_branch_id': branch_id,
        'selected_category': category,
        'selected_date_filter': date_filter,
    }

    # Group logs based on preference
    if group_by == 'branch':
        context['grouped_logs'] = group_logs_by_branch(logs)
        context['group_key'] = 'branch'
    elif group_by == 'category':
        context['grouped_logs'] = [(cat_label, logs.filter(category=cat_value))
                                   for cat_value, cat_label in ActivityLog.Category.choices]
        context['grouped_logs'] = [(name, logs_qs)
                                   for name, logs_qs in context['grouped_logs'] if logs_qs.exists()]
        context['group_key'] = 'category'
    else:  # default: group by date
        context['grouped_logs'] = group_logs_by_date(logs)
        context['group_key'] = 'date'

    return render(request, 'inventory/activity_logs.html', context)


@login_required
@module_permission_required('activity_logs', 'DELETE')
def delete_activity_log(request, pk):
    """Delete a single activity log entry."""
    if request.method == 'POST':
        log = get_object_or_404(ActivityLog, pk=pk)
        log.delete()
        messages.success(request, 'Activity log entry deleted successfully.')
    return redirect('inventory:activity_logs')


@login_required
@module_permission_required('activity_logs', 'DELETE')
def clear_activity_logs(request):
    """Clear activity logs based on filters or all logs."""
    if request.method == 'POST':
        logs = ActivityLog.objects.all()

        # Apply filters from POST data
        date_filter = request.POST.get('date_filter', 'all')
        branch_id = request.POST.get('branch_id')
        category = request.POST.get('category')

        now = timezone.now()
        today = now.date()

        # Filter by date
        if date_filter == 'today':
            logs = logs.filter(timestamp__date=today)
        elif date_filter == 'yesterday':
            yesterday = today - timedelta(days=1)
            logs = logs.filter(timestamp__date=yesterday)
        elif date_filter == 'week':
            week_start = today - timedelta(days=today.weekday())
            logs = logs.filter(timestamp__date__gte=week_start)
        elif date_filter == 'month':
            month_start = today.replace(day=1)
            logs = logs.filter(timestamp__date__gte=month_start)
        elif date_filter == 'older':
            month_start = today.replace(day=1)
            logs = logs.filter(timestamp__date__lt=month_start)

        # Filter by branch
        if branch_id:
            if branch_id == 'system':
                logs = logs.filter(branch__isnull=True)
            else:
                logs = logs.filter(branch_id=branch_id)

        # Filter by category
        if category and category != 'all':
            logs = logs.filter(category=category)

        count = logs.count()
        logs.delete()

        messages.success(
            request, f'Successfully cleared {count} activity log(s).')

    return redirect('inventory:activity_logs')


@login_required
@module_permission_required('inventory', 'VIEW')
def get_branch_products(request, branch_id):
    """
    AJAX endpoint to get products for a specific branch.
    Returns JSON with list of products in the branch.
    """
    branch = get_object_or_404(Branch, pk=branch_id, is_active=True)

    products = Product.objects.filter(
        branch=branch,
        is_deleted=False
    ).order_by('name').values('id', 'name')

    return JsonResponse({
        'branch_id': branch_id,
        'branch_name': branch.name,
        'products': list(products)
    })
