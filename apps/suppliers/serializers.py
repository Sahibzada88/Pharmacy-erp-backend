from django.db import transaction
from rest_framework import serializers
from .models import Supplier, PurchaseOrder, PurchaseOrderItem, SupplierPayment
from apps.inventory.models import Batch, StockMovement
from apps.accounts.mixins import BranchAutoAssignSerializerMixin


class SupplierSerializer(serializers.ModelSerializer):
    total_payable = serializers.SerializerMethodField()

    class Meta:
        model = Supplier
        fields = [
            'id', 'name', 'contact_person', 'phone', 'email', 'address',
            'is_active', 'total_payable', 'created_at',
        ]

    def get_total_payable(self, obj):
        """Chain-wide: total owed to this supplier across all POs."""
        total_cost = sum(po.total_amount for po in obj.purchase_orders.exclude(status='CANCELLED'))
        total_paid = sum(p.amount for p in obj.payments.all())
        return total_cost - total_paid


class PurchaseOrderItemSerializer(serializers.ModelSerializer):
    medicine_name = serializers.CharField(source='medicine.name', read_only=True)
    line_total = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)

    class Meta:
        model = PurchaseOrderItem
        fields = [
            'id', 'medicine', 'medicine_name', 'quantity_ordered', 'quantity_received',
            'unit_cost', 'unit_sale_price', 'batch_number', 'expiry_date', 'line_total',
        ]


class PurchaseOrderSerializer(BranchAutoAssignSerializerMixin, serializers.ModelSerializer):
    items = PurchaseOrderItemSerializer(many=True)
    supplier_name = serializers.CharField(source='supplier.name', read_only=True)
    branch_name = serializers.CharField(source='branch.name', read_only=True)
    total_amount = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    amount_paid = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    balance_due = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)

    class Meta:
        model = PurchaseOrder
        fields = [
            'id', 'branch', 'branch_name', 'supplier', 'supplier_name', 'po_number',
            'status', 'order_date', 'expected_date', 'received_date', 'notes',
            'items', 'total_amount', 'amount_paid', 'balance_due', 'created_at',
        ]
        read_only_fields = ['order_date', 'created_at']
        extra_kwargs = {'branch': {'required': False}}

    def create(self, validated_data):
        items_data = validated_data.pop('items')
        request = self.context['request']
        with transaction.atomic():
            po = PurchaseOrder.objects.create(created_by=request.user, **validated_data)
            for item in items_data:
                PurchaseOrderItem.objects.create(purchase_order=po, **item)
        return po

    def update(self, instance, validated_data):
        items_data = validated_data.pop('items', None)
        with transaction.atomic():
            for attr, value in validated_data.items():
                setattr(instance, attr, value)
            instance.save()
            if items_data is not None:
                instance.items.all().delete()
                for item in items_data:
                    PurchaseOrderItem.objects.create(purchase_order=instance, **item)
        return instance


class ReceivePurchaseOrderSerializer(serializers.Serializer):
    """
    Marks a PO (or specific items) as received: creates inventory Batch rows
    and StockMovement(PURCHASE_IN) entries. This is the bridge between
    Suppliers and Inventory.
    """
    item_ids = serializers.ListField(child=serializers.IntegerField(), required=False,
                                      help_text="Optional subset of item IDs to receive; default = all remaining")

    def save(self, **kwargs):
        po = self.context['purchase_order']
        user = self.context['request'].user
        item_ids = self.validated_data.get('item_ids')
        items = po.items.all()
        if item_ids:
            items = items.filter(id__in=item_ids)

        created_batches = []
        with transaction.atomic():
            for item in items:
                remaining_to_receive = item.quantity_ordered - item.quantity_received
                if remaining_to_receive <= 0:
                    continue
                batch = Batch.objects.create(
                    medicine=item.medicine,
                    branch=po.branch,
                    batch_number=item.batch_number or f"{po.po_number}-{item.id}",
                    purchase_order_item=item,
                    quantity_received=remaining_to_receive,
                    quantity_remaining=remaining_to_receive,
                    cost_price=item.unit_cost,
                    sale_price=item.unit_sale_price,
                    expiry_date=item.expiry_date,
                )
                StockMovement.objects.create(
                    batch=batch, branch=po.branch,
                    movement_type=StockMovement.MovementType.PURCHASE_IN,
                    quantity=remaining_to_receive, reference=po.po_number,
                    created_by=user,
                )
                item.quantity_received = item.quantity_ordered
                item.save(update_fields=['quantity_received'])
                created_batches.append(batch)

            total_ordered = sum(i.quantity_ordered for i in po.items.all())
            total_received = sum(i.quantity_received for i in po.items.all())
            if total_received >= total_ordered:
                po.status = PurchaseOrder.Status.RECEIVED
                from django.utils import timezone
                po.received_date = timezone.now().date()
            elif total_received > 0:
                po.status = PurchaseOrder.Status.PARTIALLY_RECEIVED
            po.save(update_fields=['status', 'received_date'])

        return created_batches


class SupplierPaymentSerializer(BranchAutoAssignSerializerMixin, serializers.ModelSerializer):
    supplier_name = serializers.CharField(source='supplier.name', read_only=True)
    branch_name = serializers.CharField(source='branch.name', read_only=True)

    class Meta:
        model = SupplierPayment
        fields = [
            'id', 'supplier', 'supplier_name', 'purchase_order', 'branch', 'branch_name',
            'bank_account', 'amount', 'method', 'reference_number', 'paid_on', 'note',
            'created_by', 'created_at',
        ]
        read_only_fields = ['paid_on', 'created_by', 'created_at']
        extra_kwargs = {'branch': {'required': False}}

    def create(self, validated_data):
        request = self.context['request']
        return SupplierPayment.objects.create(created_by=request.user, **validated_data)
