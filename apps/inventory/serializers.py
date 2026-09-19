from rest_framework import serializers
from .models import Category, Manufacturer, Medicine, Batch, StockMovement
from apps.accounts.mixins import BranchAutoAssignSerializerMixin


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'name', 'description']


class ManufacturerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Manufacturer
        fields = ['id', 'name', 'country']


class MedicineSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True, default=None)
    manufacturer_name = serializers.CharField(source='manufacturer.name', read_only=True, default=None)
    total_stock = serializers.SerializerMethodField()

    class Meta:
        model = Medicine
        fields = [
            'id', 'name', 'generic_name', 'sku', 'barcode', 'category', 'category_name',
            'manufacturer', 'manufacturer_name', 'unit_type', 'pack_size',
            'requires_prescription', 'is_active', 'reorder_level', 'total_stock',
            'created_at', 'updated_at',
        ]

    def get_total_stock(self, obj):
        # Sum of remaining quantity across active batches (optionally scoped to a branch
        # via ?branch=<id> query param, handled in the view's annotate step).
        request = self.context.get('request')
        qs = obj.batches.filter(is_active=True)
        branch_id = request.query_params.get('branch') if request else None
        if branch_id:
            qs = qs.filter(branch_id=branch_id)
        return sum(b.quantity_remaining for b in qs)


class BatchSerializer(BranchAutoAssignSerializerMixin, serializers.ModelSerializer):
    medicine_name = serializers.CharField(source='medicine.name', read_only=True)
    branch_name = serializers.CharField(source='branch.name', read_only=True)
    stock_value = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    is_expired = serializers.SerializerMethodField()
    is_near_expiry = serializers.SerializerMethodField()

    class Meta:
        model = Batch
        fields = [
            'id', 'medicine', 'medicine_name', 'branch', 'branch_name', 'batch_number',
            'purchase_order_item', 'quantity_received', 'quantity_remaining',
            'cost_price', 'sale_price', 'expiry_date', 'received_date',
            'is_active', 'stock_value', 'is_expired', 'is_near_expiry',
        ]
        read_only_fields = ['received_date']
        extra_kwargs = {'branch': {'required': False}}

    def get_is_expired(self, obj):
        from django.utils import timezone
        return obj.expiry_date < timezone.now().date()

    def get_is_near_expiry(self, obj):
        from django.utils import timezone
        from datetime import timedelta
        return obj.expiry_date <= timezone.now().date() + timedelta(days=60)


class StockMovementSerializer(serializers.ModelSerializer):
    medicine_name = serializers.CharField(source='batch.medicine.name', read_only=True)
    branch_name = serializers.CharField(source='branch.name', read_only=True)
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)

    class Meta:
        model = StockMovement
        fields = [
            'id', 'batch', 'medicine_name', 'branch', 'branch_name', 'movement_type',
            'quantity', 'reference', 'note', 'created_by', 'created_by_name', 'created_at',
        ]
        read_only_fields = ['created_at', 'created_by']


class StockAdjustmentSerializer(serializers.Serializer):
    """Used for manual write-offs (damaged/expired) or corrections."""
    batch = serializers.PrimaryKeyRelatedField(queryset=Batch.objects.all())
    quantity = serializers.IntegerField(help_text="Positive number to reduce/increase by")
    movement_type = serializers.ChoiceField(choices=[
        StockMovement.MovementType.ADJUSTMENT,
        StockMovement.MovementType.EXPIRED_WRITE_OFF,
        StockMovement.MovementType.DAMAGED_WRITE_OFF,
    ])
    note = serializers.CharField(required=False, allow_blank=True)


class StockTransferSerializer(serializers.Serializer):
    """Owner/manager moves stock of a batch from one branch to another."""
    batch = serializers.PrimaryKeyRelatedField(queryset=Batch.objects.all())
    to_branch = serializers.IntegerField(help_text="ID of the destination branch")
    quantity = serializers.IntegerField(min_value=1)

    def validate_to_branch(self, value):
        from apps.branches.models import Branch
        try:
            return Branch.objects.get(pk=value)
        except Branch.DoesNotExist:
            raise serializers.ValidationError("Destination branch not found.")
