from django.db import transaction
from django.db.models import F
from django.utils import timezone
from datetime import timedelta, datetime
import csv
import io

from rest_framework import viewsets, permissions, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser
from django_filters.rest_framework import DjangoFilterBackend

from .models import Category, Manufacturer, Medicine, Batch, StockMovement
from .serializers import (
    CategorySerializer, ManufacturerSerializer, MedicineSerializer, BatchSerializer,
    StockMovementSerializer, StockAdjustmentSerializer, StockTransferSerializer,
)
from apps.accounts.permissions import IsPharmacistOrAbove, IsOwnerOrManager
from apps.accounts.mixins import BranchScopedQuerysetMixin
from apps.branches.models import Branch


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


class RowImportError(Exception):
    """Raised for a single bad row during bulk import — caught per-row so the
    rest of the file keeps processing."""
    pass


class BulkImportMedicinesView(APIView):
    """
    POST /api/inventory/medicines/bulk-import/
    Upload a CSV file to create/update many medicines at once — and, for any
    row that also includes stock columns, create an initial inventory batch
    at the same time. This is the fast path for onboarding a pharmacy's full
    catalog instead of adding items one by one through the UI.

    Expected CSV columns (header row required, order doesn't matter):
        name*, generic_name, sku*, barcode, category, manufacturer,
        unit_type, pack_size, reorder_level, requires_prescription,
        branch_code, batch_number, quantity, cost_price, sale_price, expiry_date

    (* = required columns)

    - `sku` is the upsert key: re-uploading the same file updates existing
      medicines instead of duplicating them.
    - `category` / `manufacturer` are matched/created by name automatically.
    - Stock columns (`branch_code`, `quantity`, `cost_price`, `sale_price`,
      `expiry_date`) are all-or-nothing per row: provide all four (plus a
      valid branch_code) to also create an opening stock batch, or leave all
      of them blank to import the medicine without any stock yet.
    - Every row is processed independently — one bad row is reported as an
      error but does not stop the rest of the file from importing.
    """
    permission_classes = [IsPharmacistOrAbove]
    parser_classes = [MultiPartParser]

    REQUIRED_COLUMNS = {'name', 'sku'}
    STOCK_COLUMNS = ('branch_code', 'quantity', 'cost_price', 'sale_price', 'expiry_date')

    def post(self, request):
        file_obj = request.FILES.get('file')
        if not file_obj:
            return Response({'detail': "No file uploaded. Attach a CSV file under the 'file' field."},
                             status=status.HTTP_400_BAD_REQUEST)

        try:
            decoded = file_obj.read().decode('utf-8-sig')
        except UnicodeDecodeError:
            return Response({'detail': 'Could not read the file. Please save it as UTF-8 CSV and try again.'},
                             status=status.HTTP_400_BAD_REQUEST)

        reader = csv.DictReader(io.StringIO(decoded))
        if reader.fieldnames is None:
            return Response({'detail': 'The file appears to be empty.'}, status=status.HTTP_400_BAD_REQUEST)

        headers = {h.strip().lower() for h in reader.fieldnames}
        missing = self.REQUIRED_COLUMNS - headers
        if missing:
            return Response(
                {'detail': f"Missing required column(s): {', '.join(sorted(missing))}."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        created_medicines = 0
        updated_medicines = 0
        created_batches = 0
        errors = []

        branch_cache = {}
        category_cache = {}
        manufacturer_cache = {}

        for row_num, raw_row in enumerate(reader, start=2):  # row 1 is the header
            row = {(k or '').strip().lower(): (v or '').strip() for k, v in raw_row.items()}
            try:
                with transaction.atomic():
                    result = self._import_row(row, branch_cache, category_cache, manufacturer_cache)
            except RowImportError as e:
                errors.append({'row': row_num, 'error': str(e)})
                continue
            except Exception as e:  # noqa: BLE001 — surface any unexpected error per-row, never abort the batch
                errors.append({'row': row_num, 'error': f'Unexpected error: {e}'})
                continue

            if result['medicine_created']:
                created_medicines += 1
            else:
                updated_medicines += 1
            if result['batch_created']:
                created_batches += 1

        return Response({
            'created_medicines': created_medicines,
            'updated_medicines': updated_medicines,
            'created_batches': created_batches,
            'total_rows': created_medicines + updated_medicines + len(errors),
            'error_count': len(errors),
            'errors': errors,
        })

    def _import_row(self, row, branch_cache, category_cache, manufacturer_cache):
        """Imports one CSV row. Returns {'medicine_created': bool, 'batch_created': bool}."""
        result = {'medicine_created': False, 'batch_created': False}

        name = row.get('name')
        sku = row.get('sku')
        if not name or not sku:
            raise RowImportError("'name' and 'sku' are required.")

        category = None
        if row.get('category'):
            key = row['category'].lower()
            if key not in category_cache:
                category_cache[key], _ = Category.objects.get_or_create(name=row['category'])
            category = category_cache[key]

        manufacturer = None
        if row.get('manufacturer'):
            key = row['manufacturer'].lower()
            if key not in manufacturer_cache:
                manufacturer_cache[key], _ = Manufacturer.objects.get_or_create(name=row['manufacturer'])
            manufacturer = manufacturer_cache[key]

        unit_type = (row.get('unit_type') or Medicine.UnitType.TABLET).upper()
        if unit_type not in Medicine.UnitType.values:
            raise RowImportError(
                f"Invalid unit_type '{unit_type}'. Must be one of: {', '.join(Medicine.UnitType.values)}."
            )

        reorder_level_raw = row.get('reorder_level') or '10'
        try:
            reorder_level = int(reorder_level_raw)
        except ValueError:
            raise RowImportError(f"Invalid reorder_level '{reorder_level_raw}' — must be a whole number.")

        requires_rx = (row.get('requires_prescription') or '').lower() in ('true', '1', 'yes', 'y')

        medicine, created = Medicine.objects.update_or_create(
            sku=sku,
            defaults=dict(
                name=name,
                generic_name=row.get('generic_name', ''),
                barcode=row.get('barcode', ''),
                category=category,
                manufacturer=manufacturer,
                unit_type=unit_type,
                pack_size=row.get('pack_size', ''),
                reorder_level=reorder_level,
                requires_prescription=requires_rx,
            ),
        )
        result['medicine_created'] = created

        # Optional opening stock batch — only if ALL stock columns are filled in.
        stock_values = {col: row.get(col, '') for col in self.STOCK_COLUMNS}
        filled = [v for v in stock_values.values() if v]
        if not filled:
            return result  # no stock info for this row — medicine-only import, that's fine
        if len(filled) != len(self.STOCK_COLUMNS):
            raise RowImportError(
                "Partial stock columns provided — fill in ALL of branch_code, quantity, "
                "cost_price, sale_price and expiry_date to create opening stock, or leave "
                "all five blank to import the medicine without stock."
            )

        branch_code = stock_values['branch_code']
        if branch_code not in branch_cache:
            try:
                branch_cache[branch_code] = Branch.objects.get(code=branch_code)
            except Branch.DoesNotExist:
                raise RowImportError(f"Branch code '{branch_code}' does not exist.")
        branch = branch_cache[branch_code]

        try:
            quantity = int(stock_values['quantity'])
            cost_price = float(stock_values['cost_price'])
            sale_price = float(stock_values['sale_price'])
        except ValueError:
            raise RowImportError("quantity/cost_price/sale_price must be numbers.")

        try:
            expiry_date = datetime.strptime(stock_values['expiry_date'], '%Y-%m-%d').date()
        except ValueError:
            raise RowImportError(f"Invalid expiry_date '{stock_values['expiry_date']}' — use YYYY-MM-DD format.")

        batch_number = row.get('batch_number') or f"IMPORT-{sku}-{timezone.now().strftime('%Y%m%d%H%M%S')}"

        batch = Batch.objects.create(
            medicine=medicine, branch=branch, batch_number=batch_number,
            quantity_received=quantity, quantity_remaining=quantity,
            cost_price=cost_price, sale_price=sale_price, expiry_date=expiry_date,
        )
        StockMovement.objects.create(
            batch=batch, branch=branch, movement_type=StockMovement.MovementType.PURCHASE_IN,
            quantity=quantity, reference='BULK_IMPORT',
        )
        result['batch_created'] = True
        return result
