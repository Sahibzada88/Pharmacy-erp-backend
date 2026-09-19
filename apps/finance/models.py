from decimal import Decimal
from django.db import models
from django.core.validators import MinValueValidator


class BankAccount(models.Model):
    """A bank account owned by the pharmacy chain (or a specific branch)."""
    branch = models.ForeignKey(
        'branches.Branch', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='bank_accounts', help_text="Leave blank for a chain-wide/head-office account"
    )
    bank_name = models.CharField(max_length=100)
    account_title = models.CharField(max_length=150)
    account_number = models.CharField(max_length=50, unique=True)
    iban = models.CharField(max_length=50, blank=True)
    current_balance = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'finance_bank_account'
        ordering = ['bank_name']

    def __str__(self):
        return f"{self.bank_name} - {self.account_number}"


class BankTransaction(models.Model):
    """
    Every movement of money in/out of a bank account: cash deposits from branches,
    supplier payments out, owner withdrawals, misc income/expense.
    """

    class TxType(models.TextChoices):
        DEPOSIT = 'DEPOSIT', 'Cash Deposit (branch -> bank)'
        WITHDRAWAL = 'WITHDRAWAL', 'Withdrawal'
        SUPPLIER_PAYMENT = 'SUPPLIER_PAYMENT', 'Supplier Payment'
        SALARY_PAYMENT = 'SALARY_PAYMENT', 'Salary Payment'
        EXPENSE_PAYMENT = 'EXPENSE_PAYMENT', 'Expense Payment'
        TRANSFER_IN = 'TRANSFER_IN', 'Transfer In (between own accounts)'
        TRANSFER_OUT = 'TRANSFER_OUT', 'Transfer Out (between own accounts)'
        OTHER_INCOME = 'OTHER_INCOME', 'Other Income'

    bank_account = models.ForeignKey(BankAccount, on_delete=models.CASCADE, related_name='transactions')
    branch = models.ForeignKey('branches.Branch', null=True, blank=True, on_delete=models.SET_NULL, related_name='bank_transactions')
    tx_type = models.CharField(max_length=25, choices=TxType.choices)
    amount = models.DecimalField(max_digits=16, decimal_places=2, validators=[MinValueValidator(Decimal('0'))])
    reference_number = models.CharField(max_length=100, blank=True)
    note = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey('accounts.User', null=True, on_delete=models.SET_NULL, related_name='bank_transactions_made')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'finance_bank_transaction'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['bank_account', 'tx_type']),
            models.Index(fields=['branch']),
        ]

    def __str__(self):
        return f"{self.tx_type} {self.amount} on {self.bank_account}"

    @property
    def is_inflow(self):
        return self.tx_type in (self.TxType.DEPOSIT, self.TxType.TRANSFER_IN, self.TxType.OTHER_INCOME)


class CashRegister(models.Model):
    """
    Daily cash-drawer session per branch: opening balance, expected vs counted
    closing balance (for reconciliation / shortage-overage tracking).
    """

    class Status(models.TextChoices):
        OPEN = 'OPEN', 'Open'
        CLOSED = 'CLOSED', 'Closed'

    branch = models.ForeignKey('branches.Branch', on_delete=models.CASCADE, related_name='cash_registers')
    opened_by = models.ForeignKey('accounts.User', on_delete=models.PROTECT, related_name='registers_opened')
    closed_by = models.ForeignKey('accounts.User', null=True, blank=True, on_delete=models.SET_NULL, related_name='registers_closed')
    opening_balance = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    expected_closing_balance = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    counted_closing_balance = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    opened_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'finance_cash_register'
        ordering = ['-opened_at']

    def __str__(self):
        return f"Register {self.branch.code} - {self.opened_at.date()}"

    @property
    def variance(self):
        if self.counted_closing_balance is None or self.expected_closing_balance is None:
            return None
        return self.counted_closing_balance - self.expected_closing_balance


class ExpenseCategory(models.Model):
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        db_table = 'finance_expense_category'
        verbose_name_plural = 'Expense Categories'

    def __str__(self):
        return self.name


class Expense(models.Model):
    """Operational expenses per branch: rent, utilities, salaries, misc."""

    class PaidFrom(models.TextChoices):
        CASH = 'CASH', 'Cash Register'
        BANK = 'BANK', 'Bank Account'

    branch = models.ForeignKey('branches.Branch', on_delete=models.CASCADE, related_name='expenses')
    category = models.ForeignKey(ExpenseCategory, on_delete=models.PROTECT, related_name='expenses')
    amount = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal('0'))])
    paid_from = models.CharField(max_length=10, choices=PaidFrom.choices, default=PaidFrom.CASH)
    bank_account = models.ForeignKey(BankAccount, null=True, blank=True, on_delete=models.SET_NULL, related_name='expenses')
    description = models.CharField(max_length=255, blank=True)
    expense_date = models.DateField(auto_now_add=True)
    created_by = models.ForeignKey('accounts.User', null=True, on_delete=models.SET_NULL, related_name='expenses_recorded')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'finance_expense'
        ordering = ['-expense_date']
        indexes = [
            models.Index(fields=['branch', 'category']),
        ]

    def __str__(self):
        return f"{self.category} - {self.amount} ({self.branch.code})"
