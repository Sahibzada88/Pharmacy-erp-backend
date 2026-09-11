from django.db import transaction
from django.db.models import F
from django.utils import timezone
from datetime import timedelta
from rest_framework import viewsets, permissions, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend

from .models import Category, Manufacturer, Medicine, Batch, StockMovement
from .serializers import (
    CategorySerializer, ManufacturerSerializer, MedicineSerializer, BatchSerializer,
    StockMovementSerializer, StockAdjustmentSerializer, StockTransferSerializer,
)
from apps.accounts.permissions import IsPharmacistOrAbove, IsOwnerOrManager
from apps.accounts.mixins import BranchScopedQuerysetMixin


class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer

    def get_permissions(self):
        if self.action in ('create', 'update', 'partial_update', 'destroy'):
            return [IsPharmacistOrAbove()]
        return [permissions.IsAuthenticated()]


class ManufacturerViewSet(viewsets.ModelViewSet):
    queryset = Manufacturer.objects.all()
    serializer_class = ManufacturerSerializer

    def get_permissions(self):
        if self.action in ('create', 'update', 'partial_update', 'destroy'):
            return [IsPharmacistOrAbove()]
        return [permissions.IsAuthenticated()]


class MedicineViewSet(viewsets.ModelViewSet):
    """Master medicine catalog — shared across the whole chain."""
    queryset = Medicine.objects.select_related('category', 'manufacturer').all()
    serializer_class = MedicineSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['category', 'manufacturer', 'unit_type', 'is_active', 'requires_prescription']
    search_fields = ['name', 'generic_name', 'sku', 'barcode']
    ordering_fields = ['name', 'created_at']

    def get_permissions(self):
        if self.action in ('create', 'update', 'partial_update', 'destroy'):
            return [IsPharmacistOrAbove()]
        return [permissions.IsAuthenticated()]

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['request'] = self.request
        return ctx

    @action(detail=False, methods=['get'])
    def low_stock(self, request):
        """Medicines whose total remaining quantity (chain-wide or per-branch) is
        at/below the reorder level. Owner can pass ?branch=<id>, others auto-scoped."""
        branch_id = request.query_params.get('branch')
        if not request.user.is_owner:
            branch_id = request.user.branch_id

        results = []
        for med in Medicine.objects.filter(is_active=True):
            batches = med.batches.filter(is_active=True)
            if branch_id:
                batches = batches.filter(branch_id=branch_id)
            total = sum(b.quantity_remaining for b in batches)
            if total <= med.reorder_level:
                results.append({
                    'medicine_id': med.id,
                    'name': med.name,
                    'sku': med.sku,
                    'total_stock': total,
                    'reorder_level': med.reorder_level,
                })
        return Response(results)


class BatchViewSet(BranchScopedQuerysetMixin, viewsets.ModelViewSet):
    """Stock batches — branch scoped. Cashiers can view (for POS lookups),
    only pharmacist/manager/owner can create/edit batches directly (usually
    batches are created automatically when a Purchase Order is received)."""
    queryset = Batch.objects.select_related('medicine', 'branch').all()
    serializer_class = BatchSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['medicine', 'branch', 'is_active']
    search_fields = ['medicine__name', 'batch_number']
    ordering_fields = ['expiry_date', 'received_date']

    def get_permissions(self):
        if self.action in ('create', 'update', 'partial_update', 'destroy'):
            return [IsPharmacistOrAbove()]
        return [permissions.IsAuthenticated()]

    @action(detail=False, methods=['get'])
    def expiring_soon(self, request):
        """Batches expiring within `days` (default 60)."""
        days = int(request.query_params.get('days', 60))
        cutoff = timezone.now().date() + timedelta(days=days)
        qs = self.filter_queryset(self.get_queryset()).filter(
            expiry_date__lte=cutoff, is_active=True, quantity_remaining__gt=0
        ).order_by('expiry_date')
        page = self.paginate_queryset(qs)
        serializer = self.get_serializer(page or qs, many=True)
        return self.get_paginated_response(serializer.data) if page is not None else Response(serializer.data)

    @action(detail=False, methods=['post'], permission_classes=[IsPharmacistOrAbove])
    @transaction.atomic
    def adjust(self, request):
        """Manual stock adjustment: damaged, expired write-off, correction."""
        serializer = StockAdjustmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        batch = Batch.objects.select_for_update().get(pk=data['batch'].pk)

        qty = data['quantity']
        if qty > batch.quantity_remaining:
            return Response({'detail': 'Adjustment quantity exceeds remaining stock.'},
                             status=status.HTTP_400_BAD_REQUEST)

        batch.quantity_remaining = F('quantity_remaining') - qty
        batch.save(update_fields=['quantity_remaining'])
        batch.refresh_from_db()

        StockMovement.objects.create(
            batch=batch, branch=batch.branch, movement_type=data['movement_type'],
            quantity=-qty, note=data.get('note', ''), created_by=request.user,
        )
        return Response(BatchSerializer(batch).data)

    @action(detail=False, methods=['post'], permission_classes=[IsOwnerOrManager])
    @transaction.atomic
    def transfer(self, request):
        """Move quantity of a batch from its current branch to another branch.
        Creates a new batch record at the destination branch (same cost/expiry)."""
        serializer = StockTransferSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        batch = Batch.objects.select_for_update().get(pk=data['batch'].pk)
        qty = data['quantity']
        to_branch = data['to_branch']

        if qty > batch.quantity_remaining:
            return Response({'detail': 'Transfer quantity exceeds remaining stock.'},
                             status=status.HTTP_400_BAD_REQUEST)
        if to_branch.id == batch.branch_id:
            return Response({'detail': 'Source and destination branch are the same.'},
                             status=status.HTTP_400_BAD_REQUEST)

        batch.quantity_remaining = F('quantity_remaining') - qty
        batch.save(update_fields=['quantity_remaining'])
        batch.refresh_from_db()

        StockMovement.objects.create(
            batch=batch, branch=batch.branch, movement_type=StockMovement.MovementType.TRANSFER_OUT,
            quantity=-qty, reference=f"TRANSFER-TO-{to_branch.code}", created_by=request.user,
        )

        new_batch = Batch.objects.create(
            medicine=batch.medicine, branch=to_branch, batch_number=batch.batch_number,
            quantity_received=qty, quantity_remaining=qty,
            cost_price=batch.cost_price, sale_price=batch.sale_price,
            expiry_date=batch.expiry_date,
        )
        StockMovement.objects.create(
            batch=new_batch, branch=to_branch, movement_type=StockMovement.MovementType.TRANSFER_IN,
            quantity=qty, reference=f"TRANSFER-FROM-{batch.branch.code}", created_by=request.user,
        )
        return Response({'detail': 'Transfer completed.', 'new_batch': BatchSerializer(new_batch).data})


class StockMovementViewSet(BranchScopedQuerysetMixin, viewsets.ReadOnlyModelViewSet):
    """Read-only audit trail — every stock change is recorded here."""
    queryset = StockMovement.objects.select_related('batch', 'batch__medicine', 'branch', 'created_by').all()
    serializer_class = StockMovementSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['movement_type', 'branch', 'batch']
    ordering_fields = ['created_at']
