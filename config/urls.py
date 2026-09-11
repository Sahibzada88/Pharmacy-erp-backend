from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from rest_framework_simplejwt.views import TokenRefreshView

from drf_yasg.views import get_schema_view
from drf_yasg import openapi
from rest_framework import permissions

schema_view = get_schema_view(
    openapi.Info(
        title="Pharmacy Chain ERP API",
        default_version='v1',
        description="Multi-branch Pharmacy ERP — Inventory, POS, Suppliers, Finance, CRM, Analytics",
    ),
    public=True,
    permission_classes=(permissions.AllowAny,),
)

urlpatterns = [
    path('admin/', admin.site.urls),

    # Auth
    path('api/auth/', include('apps.accounts.urls')),
    path('api/auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    # Domain apps
    path('api/branches/', include('apps.branches.urls')),
    path('api/inventory/', include('apps.inventory.urls')),
    path('api/suppliers/', include('apps.suppliers.urls')),
    path('api/sales/', include('apps.sales.urls')),
    path('api/finance/', include('apps.finance.urls')),
    path('api/crm/', include('apps.crm.urls')),
    path('api/analytics/', include('apps.analytics.urls')),

    # Docs
    path('api/docs/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
