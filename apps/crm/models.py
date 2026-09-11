from django.db import models


class Customer(models.Model):
    """
    A pharmacy customer. Shared chain-wide (a customer can buy at any branch),
    but `home_branch` records where they registered for branch-level reporting.
    """
    name = models.CharField(max_length=150)
    phone = models.CharField(max_length=20, unique=True)
    email = models.EmailField(blank=True)
    address = models.CharField(max_length=255, blank=True)
    home_branch = models.ForeignKey('branches.Branch', null=True, blank=True, on_delete=models.SET_NULL, related_name='customers')
    loyalty_points = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'crm_customer'
        ordering = ['name']
        indexes = [
            models.Index(fields=['phone']),
        ]

    def __str__(self):
        return f"{self.name} ({self.phone})"

    @property
    def lifetime_spend(self):
        return sum(s.total_amount for s in self.sales.exclude(status='VOIDED'))


class LoyaltyTransaction(models.Model):
    """Points earned on purchase, or redeemed for a discount."""

    class TxType(models.TextChoices):
        EARNED = 'EARNED', 'Earned'
        REDEEMED = 'REDEEMED', 'Redeemed'
        ADJUSTED = 'ADJUSTED', 'Manual Adjustment'

    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='loyalty_transactions')
    sale = models.ForeignKey('sales.Sale', null=True, blank=True, on_delete=models.SET_NULL, related_name='loyalty_transactions')
    tx_type = models.CharField(max_length=10, choices=TxType.choices)
    points = models.IntegerField(help_text="Positive for earned, negative for redeemed")
    note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'crm_loyalty_transaction'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.tx_type} {self.points} pts - {self.customer.name}"


class CustomerNote(models.Model):
    """Free-text CRM notes: allergy info, preferences, follow-up reminders, etc."""
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='notes')
    author = models.ForeignKey('accounts.User', null=True, on_delete=models.SET_NULL, related_name='customer_notes')
    note = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'crm_customer_note'
        ordering = ['-created_at']

    def __str__(self):
        return f"Note on {self.customer.name}"
