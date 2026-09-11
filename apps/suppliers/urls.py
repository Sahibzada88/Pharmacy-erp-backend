from rest_framework.routers import DefaultRouter
from .views import SupplierViewSet, PurchaseOrderViewSet, SupplierPaymentViewSet

router = DefaultRouter()
router.register('suppliers', SupplierViewSet, basename='supplier')
router.register('purchase-orders', PurchaseOrderViewSet, basename='purchase-order')
router.register('payments', SupplierPaymentViewSet, basename='supplier-payment')

urlpatterns = router.urls
