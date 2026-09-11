from rest_framework.routers import DefaultRouter
from .views import CustomerViewSet, LoyaltyTransactionViewSet, CustomerNoteViewSet

router = DefaultRouter()
router.register('customers', CustomerViewSet, basename='customer')
router.register('loyalty-transactions', LoyaltyTransactionViewSet, basename='loyalty-transaction')
router.register('notes', CustomerNoteViewSet, basename='customer-note')

urlpatterns = router.urls
