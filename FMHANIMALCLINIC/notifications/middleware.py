"""Mark module-scoped notifications read when an authorized user opens a module."""

from .models import Notification
from .utils import mark_module_notifications_read


class NotificationModuleReadMiddleware:
    """Clear the badge for a module after its authorized page is opened."""

    MODULE_CONTEXT_BY_APP = {
        'appointments': Notification.ModuleContext.APPOINTMENTS,
        'employees': Notification.ModuleContext.APPOINTMENTS,
        'patients': Notification.ModuleContext.PATIENTS,
        'records': Notification.ModuleContext.MEDICAL_RECORDS,
        'diagnostics': Notification.ModuleContext.AI_DIAGNOSTICS,
        'inventory': Notification.ModuleContext.INVENTORY,
        'inquiries': Notification.ModuleContext.INQUIRIES,
        'payroll': Notification.ModuleContext.PAYROLL,
        'pos': Notification.ModuleContext.SOA,
    }

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        user = request.user
        if not user.is_authenticated or request.method != 'GET':
            return None

        match = getattr(request, 'resolver_match', None)
        if not match:
            return None

        if match.app_name == 'inquiries' and user.is_superuser:
            return None
        if match.app_name == 'employees' and match.url_name not in {
            'schedule', 'schedule_add', 'schedule_edit', 'schedule_delete',
            'schedule_clear_all', 'recurring_list', 'recurring_add',
            'recurring_delete', 'recurring_clear_all',
        }:
            return None
        if (
            'api' in match.url_name.lower()
            or 'search' in match.url_name.lower()
            or match.url_name == 'get_branch_products'
        ):
            return None

        module_context = self.MODULE_CONTEXT_BY_APP.get(match.app_name)
        if match.app_name == 'patients' and user.is_pet_owner():
            mark_module_notifications_read(user, Notification.ModuleContext.PATIENTS)
            mark_module_notifications_read(user, Notification.ModuleContext.MEDICAL_RECORDS)
            return None
        if match.app_name == 'billing' and match.url_name in {
            'my_statements', 'my_statement_detail',
        }:
            module_context = Notification.ModuleContext.SOA

        if module_context not in Notification.visible_module_contexts_for_user(user):
            return None

        mark_module_notifications_read(user, module_context)
        return None