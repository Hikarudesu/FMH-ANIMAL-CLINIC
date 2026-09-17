"""
Main URL Configuration for the FMHANIMALCLINIC project.
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

# Import legacy URL patterns for backward compatibility
from accounts.urls import legacy_urlpatterns

urlpatterns = [
    path('admin/', admin.site.urls),

    # Public-facing pages
    path('', include('landing.urls')),

    # App URLs
    path('accounts/', include('accounts.urls')),
    path('branches/', include('branches.urls')),
    path('patients/', include('patients.urls')),
    path('appointments/', include('appointments.urls')),
    path('records/', include('records.urls')),
    path('inventory/', include('inventory.urls')),
    path('billing/', include('billing.urls')),
    path('employees/', include('employees.urls')),
    path('attendance/', include('attendance.urls')),
    path('notifications/', include('notifications.urls')),
    path('payroll/', include('payroll.urls')),
    path('pos/', include('pos.urls')),
    path('reports/', include('reports.urls')),
    path('settings/', include('settings.urls')),
    path('diagnostics/', include('diagnostics.urls')),
    path('disease-geo-mapping/', include('disease_geo_mapping.urls')),
    path('inquiries/', include('inquiries.urls')),
] + legacy_urlpatterns  # Add legacy URL names for backward compatibility

# Serve static and media files in development
if settings.DEBUG:
    urlpatterns += static(
        settings.STATIC_URL,
        document_root=settings.STATICFILES_DIRS[0] if settings.STATICFILES_DIRS else None
    )

# Railway mounts uploaded files at MEDIA_ROOT. Keep media URLs available in
# production so images uploaded through Content Management remain editable.
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
