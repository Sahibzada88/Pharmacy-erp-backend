from decimal import Decimal
from django.db import models
from django.core.validators import MinValueValidator


class Supplier(models.Model):
    """A medicine distributor/vendor the pharmacy chain buys stock from."""
    name = models.CharField(max_length=150)
    contact_person = models.CharField(max_length=100, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    address = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'suppliers_supplier'
        ordering = ['name']

    def __str__(self):
        return self.name


class PurchaseOrder(models.Model):
    """A purchase (stock order) from a supplier to a specific branch."""

    class Status(models.TextChoices):
        DRAFT = 'DRAFT', 'Draft'
        ORDERED = 'ORDERED', 'Ordered'
        PARTIALLY_RECEIVED = 'PARTIALLY_RECEIVED', 'Partially Received'
        RECEIVED = 'RECEIVED', 'Received'
        CANCELLED = 'CANCELLED', 'Cancelled'

    branch = models.ForeignKey('branches.Branch', on_delete=models.CASCADE, related_name='purchase_orders')
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name='purchase_orders')
    po_number = models.CharField(max_length=50, unique=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    order_date = models.DateField(auto_now_add=True)
    expected_date = models.DateField(null=True, blank=True)
    received_date = models.DateField(null=True, blank=True)
    notes = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey('accounts.User', null=True, on_delete=models.SET_NULL, related_name='purchase_orders_created')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'suppliers_purchase_order'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['branch', 'status']),
            models.Index(fields=['supplier']),
        ]

    def __str__(self):
        return f"PO {self.po_number} - {self.supplier.name}"

    @property
    def total_amount(self):
        return sum(item.quantity_ordered * item.unit_cost for item in self.items.all())

    @property
    def amount_paid(self):
        return sum(p.amount for p in self.supplier.payments.filter(purchase_order=self))

    @property
    def balance_due(self):
        return self.total_amount - self.amount_paid


class PurchaseOrderItem(models.Model):
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name='items')
    medicine = models.ForeignKey('inventory.Medicine', on_delete=models.PROTECT, related_name='purchase_order_items')
    quantity_ordered = models.PositiveIntegerField()
    quantity_received = models.PositiveIntegerField(default=0)
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal('0'))])
    unit_sale_price = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal('0'))])
    batch_number = models.CharField(max_length=100, blank=True)
    expiry_date = models.DateField(null=True, blank=True)

    class Meta:
        db_table = 'suppliers_purchase_order_item'

    def __str__(self):
        return f"{self.medicine.name} x {self.quantity_ordered}"

    @property
    def line_total(self):
        return self.quantity_ordered * self.unit_cost


class SupplierPayment(models.Model):
    """
    Money paid TO a supplier. Tracks how much of a purchase order's cost
    the pharmacy has settled, and how much is still owed (accounts payable).
    """

    class Method(models.TextChoices):
        CASH = 'CASH', 'Cash'
        BANK_TRANSFER = 'BANK_TRANSFER', 'Bank Transfer'
        CHEQUE = 'CHEQUE', 'Cheque'
        ONLINE = 'ONLINE', 'Online / Mobile Wallet'

    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE, related_name='payments')
    purchase_order = models.ForeignKey(PurchaseOrder, null=True, blank=True, on_delete=models.SET_NULL, related_name='payments')
    branch = models.ForeignKey('branches.Branch', on_delete=models.CASCADE, related_name='supplier_payments')
    bank_account = models.ForeignKey('finance.BankAccount', null=True, blank=True, on_delete=models.SET_NULL, related_name='supplier_payments')
    amount = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal('0'))])
    method = models.CharField(max_length=20, choices=Method.choices, default=Method.BANK_TRANSFER)
    reference_number = models.CharField(max_length=100, blank=True)
    paid_on = models.DateField(auto_now_add=True)
    note = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey('accounts.User', null=True, on_delete=models.SET_NULL, related_name='supplier_payments_made')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'suppliers_payment'
        ordering = ['-paid_on']
        indexes = [
            models.Index(fields=['branch']),
            models.Index(fields=['supplier']),
        ]

    def __str__(self):
        return f"{self.amount} to {self.supplier.name} on {self.paid_on}"
