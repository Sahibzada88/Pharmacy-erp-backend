from django.db import models
from django.core.validators import MinValueValidator


class Sale(models.Model):
    """A single POS transaction (an invoice/receipt)."""

    class Status(models.TextChoices):
        COMPLETED = 'COMPLETED', 'Completed'
        RETURNED = 'RETURNED', 'Returned'
        PARTIALLY_RETURNED = 'PARTIALLY_RETURNED', 'Partially Returned'
        VOIDED = 'VOIDED', 'Voided'

    branch = models.ForeignKey('branches.Branch', on_delete=models.CASCADE, related_name='sales')
    invoice_number = models.CharField(max_length=50, unique=True)
    customer = models.ForeignKey('crm.Customer', null=True, blank=True, on_delete=models.SET_NULL, related_name='sales')
    cashier = models.ForeignKey('accounts.User', on_delete=models.PROTECT, related_name='sales_made')
    subtotal = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    tax_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.COMPLETED)
    note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'sales_sale'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['branch', 'created_at']),
            models.Index(fields=['cashier']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f"Invoice {self.invoice_number} - {self.total_amount}"


class SaleItem(models.Model):
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name='items')
    batch = models.ForeignKey('inventory.Batch', on_delete=models.PROTECT, related_name='sale_items')
    medicine_name_snapshot = models.CharField(max_length=200, help_text="Snapshot at time of sale")
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    unit_cost_snapshot = models.DecimalField(max_digits=12, decimal_places=2, help_text="Cost at time of sale, for profit analytics")
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    line_total = models.DecimalField(max_digits=14, decimal_places=2)
    quantity_returned = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = 'sales_sale_item'

    def __str__(self):
        return f"{self.medicine_name_snapshot} x {self.quantity}"

    @property
    def profit(self):
        return (self.unit_price - self.unit_cost_snapshot) * (self.quantity - self.quantity_returned) - self.discount_amount


class SalePayment(models.Model):
    """A sale can be split across multiple payment methods (cash + card, etc.)."""

    class Method(models.TextChoices):
        CASH = 'CASH', 'Cash'
        CARD = 'CARD', 'Card'
        BANK_TRANSFER = 'BANK_TRANSFER', 'Bank Transfer'
        MOBILE_WALLET = 'MOBILE_WALLET', 'Mobile Wallet (Easypaisa/JazzCash)'
        CREDIT = 'CREDIT', 'Store Credit / Udhaar'

    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name='payments')
    method = models.CharField(max_length=20, choices=Method.choices)
    amount = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(0)])
    bank_account = models.ForeignKey('finance.BankAccount', null=True, blank=True, on_delete=models.SET_NULL, related_name='sale_payments')
    reference_number = models.CharField(max_length=100, blank=True)

    class Meta:
        db_table = 'sales_sale_payment'

    def __str__(self):
        return f"{self.method}: {self.amount}"


class SaleReturn(models.Model):
    """Customer return of one or more items from a completed sale."""
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name='returns')
    sale_item = models.ForeignKey(SaleItem, on_delete=models.CASCADE, related_name='returns')
    branch = models.ForeignKey('branches.Branch', on_delete=models.CASCADE, related_name='sale_returns')
    quantity = models.PositiveIntegerField()
    refund_amount = models.DecimalField(max_digits=14, decimal_places=2)
    reason = models.CharField(max_length=255, blank=True)
    processed_by = models.ForeignKey('accounts.User', null=True, on_delete=models.SET_NULL, related_name='returns_processed')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'sales_sale_return'
        ordering = ['-created_at']

    def __str__(self):
        return f"Return of {self.quantity} from Sale {self.sale.invoice_number}"
