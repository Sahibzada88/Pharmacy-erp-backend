from rest_framework.routers import DefaultRouter
from django.urls import path
from .views import SaleViewSet, CheckoutView, SaleReturnView

router = DefaultRouter()
router.register('invoices', SaleViewSet, basename='sale')

urlpatterns = [
    path('checkout/', CheckoutView.as_view(), name='pos-checkout'),
    path('returns/', SaleReturnView.as_view(), name='sale-return'),
] + router.urls
