from rest_framework import viewsets, permissions, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend

from .models import Supplier, PurchaseOrder, SupplierPayment
from .serializers import (
    SupplierSerializer, PurchaseOrderSerializer,
    ReceivePurchaseOrderSerializer, SupplierPaymentSerializer,
)
from apps.accounts.permissions import IsOwnerOrManager, IsOwnerOrAccountant
from apps.accounts.mixins import BranchScopedQuerysetMixin


class SupplierViewSet(viewsets.ModelViewSet):
    """Suppliers are chain-wide (not branch-scoped) since one supplier serves many branches."""
    queryset = Supplier.objects.all()
    serializer_class = SupplierSerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ['name', 'contact_person', 'phone']

    def get_permissions(self):
        if self.action in ('create', 'update', 'partial_update', 'destroy'):
            return [IsOwnerOrManager()]
        return [permissions.IsAuthenticated()]


class PurchaseOrderViewSet(BranchScopedQuerysetMixin, viewsets.ModelViewSet):
    queryset = PurchaseOrder.objects.select_related('branch', 'supplier').prefetch_related('items').all()
    serializer_class = PurchaseOrderSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['branch', 'supplier', 'status']
    search_fields = ['po_number']
    ordering_fields = ['order_date', 'created_at']

    def get_permissions(self):
        if self.action in ('create', 'update', 'partial_update', 'destroy', 'receive'):
            return [IsOwnerOrManager()]
        return [permissions.IsAuthenticated()]

    @action(detail=True, methods=['post'])
    def receive(self, request, pk=None):
        """Mark PO (fully or partially) received -> auto-creates inventory batches."""
        po = self.get_object()
        serializer = ReceivePurchaseOrderSerializer(
            data=request.data, context={'purchase_order': po, 'request': request}
        )
        serializer.is_valid(raise_exception=True)
        batches = serializer.save()
        return Response({
            'detail': f'{len(batches)} batch(es) received into inventory.',
            'purchase_order': PurchaseOrderSerializer(po).data,
        })


class SupplierPaymentViewSet(BranchScopedQuerysetMixin, viewsets.ModelViewSet):
    """Payments made TO suppliers — feeds finance & analytics ('kitne supplier ko dene hain')."""
    queryset = SupplierPayment.objects.select_related('supplier', 'branch', 'bank_account').all()
    serializer_class = SupplierPaymentSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['branch', 'supplier', 'method']
    ordering_fields = ['paid_on', 'created_at']

    def get_permissions(self):
        if self.action in ('create', 'update', 'partial_update', 'destroy'):
            return [IsOwnerOrAccountant()]
        return [permissions.IsAuthenticated()]
