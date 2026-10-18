"""Compatibility middleware placeholder; opening a module does not mark alerts read."""


class NotificationModuleReadMiddleware:
    """Retained as a no-op to avoid breaking external middleware references."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        return None