from django.db import transaction
from django.db.models import F
from rest_framework import serializers

from .models import Sale, SaleItem, SalePayment, SaleReturn
from apps.inventory.models import Batch, StockMovement


class SalePaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = SalePayment
        fields = ['id', 'method', 'amount', 'bank_account', 'reference_number']


class SaleItemSerializer(serializers.ModelSerializer):
    profit = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)

    class Meta:
        model = SaleItem
        fields = [
            'id', 'batch', 'medicine_name_snapshot', 'quantity', 'unit_price',
            'unit_cost_snapshot', 'discount_amount', 'line_total',
            'quantity_returned', 'profit',
        ]
        read_only_fields = ['medicine_name_snapshot', 'unit_cost_snapshot', 'line_total', 'quantity_returned']


class SaleSerializer(serializers.ModelSerializer):
    """Read serializer — full invoice with items and payments."""
    items = SaleItemSerializer(many=True, read_only=True)
    payments = SalePaymentSerializer(many=True, read_only=True)
    cashier_name = serializers.CharField(source='cashier.get_full_name', read_only=True)
    branch_name = serializers.CharField(source='branch.name', read_only=True)
    customer_name = serializers.CharField(source='customer.name', read_only=True, default=None)

    class Meta:
        model = Sale
        fields = [
            'id', 'branch', 'branch_name', 'invoice_number', 'customer', 'customer_name',
            'cashier', 'cashier_name', 'subtotal', 'discount_amount', 'tax_amount',
            'total_amount', 'status', 'note', 'items', 'payments', 'created_at',
        ]
        read_only_fields = ['invoice_number', 'cashier', 'subtotal', 'total_amount', 'status', 'created_at']


class CartItemInputSerializer(serializers.Serializer):
    """One line item from the POS cart, sent by the cashier's frontend."""
    medicine_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1)
    discount_amount = serializers.DecimalField(max_digits=12, decimal_places=2, default=0, required=False)
    # Optional: force a specific batch (e.g. cashier scans a specific pack). If omitted,
    # FEFO (first-expiry-first-out) picks the soonest-expiring batch(es) automatically.
    batch_id = serializers.IntegerField(required=False, allow_null=True)


class CheckoutSerializer(serializers.Serializer):
    """
    POS checkout endpoint payload: cart items + payment split.
    Handles: FEFO batch deduction, stock movement logging, invoice numbering,
    and multi-method payment (cash/card/bank/wallet/credit).
    """
    branch = serializers.IntegerField(
        required=False, allow_null=True,
        help_text="Required ONLY if the logged-in user is OWNER (who has no home "
                   "branch and must say which branch this sale is for). Ignored "
                   "for cashier/manager/accountant/pharmacist — they always sell "
                   "from their own assigned branch."
    )
    customer = serializers.IntegerField(required=False, allow_null=True)
    items = CartItemInputSerializer(many=True)
    payments = SalePaymentSerializer(many=True)
    discount_amount = serializers.DecimalField(max_digits=14, decimal_places=2, default=0, required=False)
    tax_amount = serializers.DecimalField(max_digits=14, decimal_places=2, default=0, required=False)
    note = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        if not attrs.get('items'):
            raise serializers.ValidationError("Cart cannot be empty.")
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        request = self.context['request']
        user = request.user

        if user.is_owner:
            branch_id = validated_data.get('branch')
            if not branch_id:
                raise serializers.ValidationError({
                    'branch': 'Owner has no home branch — specify which branch this sale is for '
                              '(e.g. "branch": 1 in the request body).'
                })
            from apps.branches.models import Branch
            try:
                branch = Branch.objects.get(pk=branch_id)
            except Branch.DoesNotExist:
                raise serializers.ValidationError({'branch': 'Branch not found.'})
        else:
            branch = user.branch
            if branch is None:
                raise serializers.ValidationError(
                    "Your account is not assigned to any branch. Ask the owner/manager to assign one."
                )

        items_data = validated_data['items']
        payments_data = validated_data['payments']

        sale = Sale.objects.create(
            branch=branch,
            invoice_number=self._generate_invoice_number(branch),
            customer_id=validated_data.get('customer'),
            cashier=user,
            discount_amount=validated_data.get('discount_amount', 0),
            tax_amount=validated_data.get('tax_amount', 0),
            note=validated_data.get('note', ''),
        )

        subtotal = 0
        for item in items_data:
            remaining_qty = item['quantity']
            batches_qs = Batch.objects.select_for_update().filter(
                medicine_id=item['medicine_id'], branch=branch,
                is_active=True, quantity_remaining__gt=0,
            ).order_by('expiry_date')  # FEFO

            if item.get('batch_id'):
                batches_qs = batches_qs.filter(id=item['batch_id'])

            batches = list(batches_qs)
            if not batches:
                raise serializers.ValidationError(
                    f"No available stock for medicine id={item['medicine_id']} at this branch."
                )

            total_available = sum(b.quantity_remaining for b in batches)
            if total_available < remaining_qty:
                raise serializers.ValidationError(
                    f"Insufficient stock for medicine id={item['medicine_id']}. "
                    f"Requested {remaining_qty}, available {total_available}."
                )

            per_item_discount = item.get('discount_amount', 0)
            for batch in batches:
                if remaining_qty <= 0:
                    break
                take = min(batch.quantity_remaining, remaining_qty)

                line_total = (batch.sale_price * take) - per_item_discount
                sale_item = SaleItem.objects.create(
                    sale=sale, batch=batch,
                    medicine_name_snapshot=batch.medicine.name,
                    quantity=take, unit_price=batch.sale_price,
                    unit_cost_snapshot=batch.cost_price,
                    discount_amount=per_item_discount if take == remaining_qty else 0,
                    line_total=line_total,
                )
                subtotal += line_total

                batch.quantity_remaining = F('quantity_remaining') - take
                batch.save(update_fields=['quantity_remaining'])

                StockMovement.objects.create(
                    batch=batch, branch=branch, movement_type=StockMovement.MovementType.SALE_OUT,
                    quantity=-take, reference=sale.invoice_number, created_by=user,
                )
                remaining_qty -= take

        sale.subtotal = subtotal
        sale.total_amount = subtotal - sale.discount_amount + sale.tax_amount
        sale.save(update_fields=['subtotal', 'total_amount'])

        total_paid = 0
        for pay in payments_data:
            SalePayment.objects.create(sale=sale, **pay)
            total_paid += pay['amount']

        if round(total_paid, 2) != round(float(sale.total_amount), 2):
            raise serializers.ValidationError(
                f"Payment total ({total_paid}) does not match sale total ({sale.total_amount})."
            )

        return sale

    @staticmethod
    def _generate_invoice_number(branch):
        import uuid
        from django.utils import timezone
        ts = timezone.now().strftime('%Y%m%d%H%M%S')
        return f"{branch.code}-{ts}-{str(uuid.uuid4())[:4].upper()}"


class SaleReturnCreateSerializer(serializers.Serializer):
    sale_item = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1)
    reason = serializers.CharField(required=False, allow_blank=True)

    @transaction.atomic
    def save(self, **kwargs):
        request = self.context['request']
        item = SaleItem.objects.select_for_update().get(pk=self.validated_data['sale_item'])
        qty = self.validated_data['quantity']

        returnable = item.quantity - item.quantity_returned
        if qty > returnable:
            raise serializers.ValidationError(f"Cannot return more than {returnable} remaining units.")

        refund_amount = (item.unit_price * qty) - (item.discount_amount if qty == returnable else 0)

        item.quantity_returned = F('quantity_returned') + qty
        item.save(update_fields=['quantity_returned'])
        item.refresh_from_db()

        batch = item.batch
        batch.quantity_remaining = F('quantity_remaining') + qty  # add returned stock back
        batch.save(update_fields=['quantity_remaining'])

        StockMovement.objects.create(
            batch=batch, branch=item.sale.branch, movement_type=StockMovement.MovementType.RETURN_IN,
            quantity=qty, reference=item.sale.invoice_number, created_by=request.user,
        )

        sale_return = SaleReturn.objects.create(
            sale=item.sale, sale_item=item, branch=item.sale.branch,
            quantity=qty, refund_amount=refund_amount,
            reason=self.validated_data.get('reason', ''), processed_by=request.user,
        )

        sale = item.sale
        if all(i.quantity_returned >= i.quantity for i in sale.items.all()):
            sale.status = Sale.Status.RETURNED
        else:
            sale.status = Sale.Status.PARTIALLY_RETURNED
        sale.save(update_fields=['status'])

        return sale_return
