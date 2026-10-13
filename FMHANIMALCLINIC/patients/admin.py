from django.contrib import admin
from utils.admin import SoftDeleteAdminMixin
from .models import Pet


@admin.register(Pet)
class PetAdmin(SoftDeleteAdminMixin, admin.ModelAdmin):
    list_display = ('name', 'species', 'breed', 'date_of_birth', 'sex', 'color', 'owner', 'created_at')
    list_filter = ('species', 'sex')
    search_fields = ('name', 'breed', 'owner__username')
