from django.contrib import admin
from .models import BankAccount, BankTransaction, CashRegister, ExpenseCategory, Expense


@admin.register(BankAccount)
class BankAccountAdmin(admin.ModelAdmin):
    list_display = ('bank_name', 'account_number', 'branch', 'current_balance', 'is_active')
    list_filter = ('bank_name', 'branch', 'is_active')


@admin.register(BankTransaction)
class BankTransactionAdmin(admin.ModelAdmin):
    list_display = ('bank_account', 'tx_type', 'amount', 'branch', 'created_at')
    list_filter = ('tx_type', 'branch')


@admin.register(CashRegister)
class CashRegisterAdmin(admin.ModelAdmin):
    list_display = ('branch', 'opened_by', 'opening_balance', 'counted_closing_balance', 'status', 'opened_at')
    list_filter = ('branch', 'status')


@admin.register(ExpenseCategory)
class ExpenseCategoryAdmin(admin.ModelAdmin):
    list_display = ('name',)


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ('branch', 'category', 'amount', 'paid_from', 'expense_date')
    list_filter = ('branch', 'category', 'paid_from')
