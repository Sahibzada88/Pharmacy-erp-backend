from decimal import Decimal
from django.db import models
from django.core.validators import MinValueValidator


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.CharField(max_length=255, blank=True)

    class Meta:
        db_table = 'inventory_category'
        ordering = ['name']
        verbose_name_plural = 'Categories'

    def __str__(self):
        return self.name


class Manufacturer(models.Model):
    name = models.CharField(max_length=150, unique=True)
    country = models.CharField(max_length=100, blank=True)

    class Meta:
        db_table = 'inventory_manufacturer'
        ordering = ['name']

    def __str__(self):
        return self.name


class Medicine(models.Model):
    """
    Master product record for a medicine/item. Actual stock quantities live in
    Batch (since medicines are bought/sold in expiry-dated batches).
    """

    class UnitType(models.TextChoices):
        TABLET = 'TABLET', 'Tablet'
        SYRUP = 'SYRUP', 'Syrup'
        INJECTION = 'INJECTION', 'Injection'
        CAPSULE = 'CAPSULE', 'Capsule'
        OINTMENT = 'OINTMENT', 'Ointment'
        DROPS = 'DROPS', 'Drops'
        OTHER = 'OTHER', 'Other'

    name = models.CharField(max_length=200, db_index=True)
    generic_name = models.CharField(max_length=200, blank=True, db_index=True)
    sku = models.CharField(max_length=64, unique=True, help_text="Internal SKU / barcode")
    barcode = models.CharField(max_length=64, blank=True, db_index=True)
    category = models.ForeignKey(Category, null=True, blank=True, on_delete=models.SET_NULL, related_name='medicines')
    manufacturer = models.ForeignKey(Manufacturer, null=True, blank=True, on_delete=models.SET_NULL, related_name='medicines')
    unit_type = models.CharField(max_length=20, choices=UnitType.choices, default=UnitType.TABLET)
    pack_size = models.CharField(max_length=50, blank=True, help_text="e.g. '10 tablets/strip'")
    requires_prescription = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    reorder_level = models.PositiveIntegerField(default=10, help_text="Chain-wide low-stock alert threshold")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'inventory_medicine'
        ordering = ['name']
        indexes = [
            models.Index(fields=['name']),
            models.Index(fields=['sku']),
        ]

    def __str__(self):
        return f"{self.name} ({self.sku})"


class Batch(models.Model):
    """
    A purchased batch of a medicine at a specific branch, with its own cost/sale
    price, expiry date and remaining quantity. Stock is always tracked per-branch,
    per-batch so FEFO (first-expiry-first-out) dispensing and expiry analytics work.
    """
    medicine = models.ForeignKey(Medicine, on_delete=models.CASCADE, related_name='batches')
    branch = models.ForeignKey('branches.Branch', on_delete=models.CASCADE, related_name='batches')
    batch_number = models.CharField(max_length=100)
    purchase_order_item = models.ForeignKey(
        'suppliers.PurchaseOrderItem', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='batches'
    )
    quantity_received = models.PositiveIntegerField()
    quantity_remaining = models.PositiveIntegerField()
    cost_price = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal('0'))])
    sale_price = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal('0'))])
    expiry_date = models.DateField(db_index=True)
    received_date = models.DateField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'inventory_batch'
        ordering = ['expiry_date']
        indexes = [
            models.Index(fields=['branch', 'medicine']),
            models.Index(fields=['expiry_date']),
        ]

    def __str__(self):
        return f"{self.medicine.name} - Batch {self.batch_number} @ {self.branch.code}"

    @property
    def stock_value(self):
        return self.quantity_remaining * self.cost_price


class StockMovement(models.Model):
    """
    Immutable audit trail of every stock change: purchase-in, sale-out,
    adjustment (damage/expiry write-off), or inter-branch transfer.
    """

    class MovementType(models.TextChoices):
        PURCHASE_IN = 'PURCHASE_IN', 'Purchase In'
        SALE_OUT = 'SALE_OUT', 'Sale Out'
        RETURN_IN = 'RETURN_IN', 'Customer Return In'
        ADJUSTMENT = 'ADJUSTMENT', 'Adjustment'
        EXPIRED_WRITE_OFF = 'EXPIRED_WRITE_OFF', 'Expired Write-off'
        DAMAGED_WRITE_OFF = 'DAMAGED_WRITE_OFF', 'Damaged Write-off'
        TRANSFER_OUT = 'TRANSFER_OUT', 'Transfer Out'
        TRANSFER_IN = 'TRANSFER_IN', 'Transfer In'

    batch = models.ForeignKey(Batch, on_delete=models.CASCADE, related_name='movements')
    branch = models.ForeignKey('branches.Branch', on_delete=models.CASCADE, related_name='stock_movements')
    movement_type = models.CharField(max_length=20, choices=MovementType.choices)
    quantity = models.IntegerField(help_text="Positive for in-movements, negative for out-movements")
    reference = models.CharField(max_length=100, blank=True, help_text="Sale/PO/Transfer reference number")
    note = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey('accounts.User', null=True, on_delete=models.SET_NULL, related_name='stock_movements')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'inventory_stock_movement'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['branch', 'movement_type']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f"{self.movement_type} {self.quantity} - {self.batch}"
