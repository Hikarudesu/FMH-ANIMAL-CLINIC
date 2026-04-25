from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Count
from django.utils import timezone
from django.urls import reverse
import json

from .models import Inquiry
from .forms import InquirySubmitForm, InquiryResponseForm
from branches.models import Branch
from notifications.utils import (
    notify_inquiry_archived,
    notify_inquiry_received,
    notify_inquiry_responded,
)


@csrf_exempt
def submit_inquiry(request):
    """
    AJAX endpoint for contact form submission.
    Accepts POST requests and creates a new inquiry.
    """
    if request.method == 'POST':
        # Handle both form data and JSON
        if request.content_type == 'application/json':
            try:
                data = json.loads(request.body)
            except json.JSONDecodeError:
                return JsonResponse({
                    'success': False,
                    'error': 'Invalid JSON data'
                }, status=400)
            
            # Validate required fields
            required_fields = ['fullName', 'email', 'phone', 'message']
            missing_fields = [field for field in required_fields if not data.get(field)]
            
            if missing_fields:
                return JsonResponse({
                    'success': False,
                    'error': f'Missing required fields: {", ".join(missing_fields)}'
                }, status=400)
            
            # Create inquiry directly from the data
            try:
                # Get branch ID, handle empty string
                branch_id = data.get('branch')
                if branch_id == '' or branch_id is None:
                    branch_id = None
                else:
                    try:
                        branch_id = int(branch_id)
                    except (ValueError, TypeError):
                        branch_id = None
                
                inquiry = Inquiry.objects.create(
                    full_name=data.get('fullName', '').strip(),
                    email=data.get('email', '').strip(),
                    phone=data.get('phone', '').strip(),
                    branch_id=branch_id,
                    message=data.get('message', '').strip(),
                    status='NEW',
                    priority='NORMAL'
                )
                notify_inquiry_received(inquiry)
                
                return JsonResponse({
                    'success': True,
                    'message': 'Your inquiry has been submitted successfully. We will contact you soon.',
                    'inquiry_id': inquiry.id
                })
            except Exception as e:
                # Log the error for debugging
                import traceback
                print(f"Error saving inquiry: {str(e)}")
                print(traceback.format_exc())
                
                return JsonResponse({
                    'success': False,
                    'error': f'Failed to save inquiry: {str(e)}'
                }, status=400)
        else:
            # Handle regular POST data
            form_data = {
                'full_name': request.POST.get('fullName', ''),
                'email': request.POST.get('email', ''),
                'phone': request.POST.get('phone', ''),
                'branch': request.POST.get('branch', ''),
                'message': request.POST.get('message', ''),
            }
            
            form = InquirySubmitForm(form_data)
            
            if form.is_valid():
                inquiry = form.save()
                notify_inquiry_received(inquiry)
                return JsonResponse({
                    'success': True,
                    'message': 'Your inquiry has been submitted successfully. We will contact you soon.',
                    'inquiry_id': inquiry.id
                })
            else:
                return JsonResponse({
                    'success': False,
                    'errors': form.errors
                }, status=400)
    
    return JsonResponse({
        'success': False,
        'error': 'Method not allowed'
    }, status=405)


@login_required
def inquiry_list(request):
    """Admin view: List all inquiries with filtering."""
    inquiries = Inquiry.objects.select_related('branch', 'responded_by').all()
    
    # Filtering
    status_filter = request.GET.get('status', '')
    priority_filter = request.GET.get('priority', '')
    branch_filter = request.GET.get('branch', '')
    search_query = request.GET.get('q', '')
    
    if status_filter:
        inquiries = inquiries.filter(status=status_filter)
    if priority_filter:
        inquiries = inquiries.filter(priority=priority_filter)
    if branch_filter:
        inquiries = inquiries.filter(branch_id=branch_filter)
    if search_query:
        inquiries = inquiries.filter(
            Q(full_name__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(phone__icontains=search_query) |
            Q(message__icontains=search_query)
        )
    
    # Get stats for sidebar
    stats = {
        'total': Inquiry.objects.count(),
        'new': Inquiry.objects.filter(status='NEW').count(),
        'read': Inquiry.objects.filter(status='READ').count(),
        'responded': Inquiry.objects.filter(status='RESPONDED').count(),
        'archived': Inquiry.objects.filter(status='ARCHIVED').count(),
    }
    
    # Pagination
    paginator = Paginator(inquiries, 20)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    
    branches = Branch.objects.filter(is_active=True)
    
    context = {
        'inquiries': page_obj,
        'stats': stats,
        'branches': branches,
        'status_choices': Inquiry.STATUS_CHOICES,
        'priority_choices': Inquiry.PRIORITY_CHOICES,
        'current_filters': {
            'status': status_filter,
            'priority': priority_filter,
            'branch': branch_filter,
            'q': search_query,
        }
    }
    
    return render(request, 'inquiries/inquiry_list.html', context)


@login_required
def inquiry_detail(request, pk):
    """Admin view: View and respond to a specific inquiry."""
    inquiry = get_object_or_404(Inquiry.objects.select_related('branch', 'responded_by'), pk=pk)
    was_responded = inquiry.status == 'RESPONDED'

    # Mark as READ if it's NEW
    if inquiry.status == 'NEW':
        inquiry.status = 'READ'
        inquiry.save(update_fields=['status', 'updated_at'])

    if request.method == 'POST':
        form = InquiryResponseForm(request.POST, instance=inquiry)
        if form.is_valid():
            inquiry = form.save(commit=False)

            # Set responded_by if responding
            if inquiry.response and not was_responded:
                inquiry.responded_by = request.user
                inquiry.response_date = timezone.now()
                if inquiry.status in {'NEW', 'READ'}:
                    inquiry.status = 'RESPONDED'

            inquiry.save()
            if not was_responded and inquiry.status == 'RESPONDED':
                notify_inquiry_responded(inquiry, request.user)
            messages.success(request, 'Inquiry updated successfully.')
            return redirect('inquiries:detail', pk=pk)
    else:
        form = InquiryResponseForm(instance=inquiry)

    # Build meta items for hero component
    meta_items = [
        {'icon': 'bx-envelope', 'label': 'Email', 'value': inquiry.email},
        {'icon': 'bx-phone', 'label': 'Phone', 'value': inquiry.phone},
    ]
    if inquiry.branch:
        meta_items.append({'icon': 'bx-building', 'label': 'Branch', 'value': inquiry.branch.name})

    context = {
        'inquiry': inquiry,
        'form': form,
        'meta_items': meta_items,
        'inquiry_list_url': reverse('inquiries:list'),
    }

    return render(request, 'inquiries/inquiry_detail.html', context)


@login_required
@require_http_methods(['POST'])
def inquiry_update_status(request, pk):
    """AJAX endpoint to quickly update inquiry status."""
    inquiry = get_object_or_404(Inquiry, pk=pk)
    
    try:
        data = json.loads(request.body)
        new_status = data.get('status')
        
        if new_status in dict(Inquiry.STATUS_CHOICES):
            previous_status = inquiry.status
            inquiry.status = new_status
            inquiry.save(update_fields=['status', 'updated_at'])
            if new_status == 'RESPONDED' and previous_status != 'RESPONDED':
                notify_inquiry_responded(inquiry, request.user)
            elif new_status == 'ARCHIVED' and previous_status != 'ARCHIVED':
                notify_inquiry_archived(inquiry, request.user)
            
            return JsonResponse({
                'success': True,
                'status': inquiry.status,
                'status_display': inquiry.get_status_display()
            })
        else:
            return JsonResponse({
                'success': False,
                'error': 'Invalid status'
            }, status=400)
            
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON data'
        }, status=400)


@login_required
@require_http_methods(['POST'])
def inquiry_bulk_action(request):
    """Handle bulk actions on inquiries."""
    try:
        data = json.loads(request.body)
        inquiry_ids = data.get('ids', [])
        action = data.get('action')
        
        if not inquiry_ids:
            return JsonResponse({
                'success': False,
                'error': 'No inquiries selected'
            }, status=400)
        
        inquiries = Inquiry.objects.filter(pk__in=inquiry_ids)
        inquiry_list = list(inquiries)
        
        if action == 'mark_read':
            inquiries.update(status='READ')
        elif action == 'mark_responded':
            notify_targets = [item for item in inquiry_list if item.status != 'RESPONDED']
            inquiries.update(status='RESPONDED')
            for inquiry in notify_targets:
                notify_inquiry_responded(inquiry, request.user)
        elif action == 'archive':
            notify_targets = [item for item in inquiry_list if item.status != 'ARCHIVED']
            inquiries.update(status='ARCHIVED')
            for inquiry in notify_targets:
                notify_inquiry_archived(inquiry, request.user)
        elif action == 'delete':
            inquiries.delete()
        else:
            return JsonResponse({
                'success': False,
                'error': 'Invalid action'
            }, status=400)
        
        return JsonResponse({
            'success': True,
            'message': f'Action "{action}" applied to {len(inquiry_ids)} inquiries'
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON data'
        }, status=400)


def get_inquiry_stats(request):
    """API endpoint to get inquiry statistics (for dashboard widget)."""
    stats = {
        'total': Inquiry.objects.count(),
        'new': Inquiry.objects.filter(status='NEW').count(),
        'today': Inquiry.objects.filter(
            created_at__date=timezone.now().date()
        ).count(),
        'this_week': Inquiry.objects.filter(
            created_at__gte=timezone.now() - timezone.timedelta(days=7)
        ).count(),
    }
    return JsonResponse(stats)
