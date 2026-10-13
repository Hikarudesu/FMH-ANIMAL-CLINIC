class SoftDeleteAdminMixin:
    """Route Django admin bulk deletes through model soft-delete methods."""

    def delete_queryset(self, request, queryset):
        for item in queryset.iterator():
            item.delete()
