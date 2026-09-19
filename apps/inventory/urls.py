from rest_framework.routers import DefaultRouter
from django.urls import path
from .views import (
    CategoryViewSet, ManufacturerViewSet, MedicineViewSet, BatchViewSet,
    StockMovementViewSet, BulkImportMedicinesView,
)

router = DefaultRouter()
router.register('categories', CategoryViewSet, basename='category')
router.register('manufacturers', ManufacturerViewSet, basename='manufacturer')
router.register('medicines', MedicineViewSet, basename='medicine')
router.register('batches', BatchViewSet, basename='batch')
router.register('stock-movements', StockMovementViewSet, basename='stock-movement')

urlpatterns = [
    path('medicines/bulk-import/', BulkImportMedicinesView.as_view(), name='medicines-bulk-import'),
] + router.urls
