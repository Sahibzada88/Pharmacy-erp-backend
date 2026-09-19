from django.db import transaction
from django.db.models import F
from rest_framework import serializers

from .models import BankAccount, BankTransaction, CashRegister, ExpenseCategory, Expense
from apps.accounts.mixins import BranchAutoAssignSerializerMixin


class BankAccountSerializer(serializers.ModelSerializer):
    branch_name = serializers.CharField(source='branch.name', read_only=True, default='Head Office')

    class Meta:
        model = BankAccount
        fields = [
            'id', 'branch', 'branch_name', 'bank_name', 'account_title',
            'account_number', 'iban', 'current_balance', 'is_active', 'created_at',
        ]
        read_only_fields = ['current_balance', 'created_at']


class BankTransactionSerializer(serializers.ModelSerializer):
    bank_name = serializers.CharField(source='bank_account.bank_name', read_only=True)
    branch_name = serializers.CharField(source='branch.name', read_only=True, default=None)
    is_inflow = serializers.BooleanField(read_only=True)

    class Meta:
        model = BankTransaction
        fields = [
            'id', 'bank_account', 'bank_name', 'branch', 'branch_name', 'tx_type',
            'amount', 'reference_number', 'note', 'is_inflow', 'created_by', 'created_at',
        ]
        read_only_fields = ['created_by', 'created_at']

    @transaction.atomic
    def create(self, validated_data):
        request = self.context['request']
        tx = BankTransaction.objects.create(created_by=request.user, **validated_data)

        account = BankAccount.objects.select_for_update().get(pk=tx.bank_account_id)
        if tx.is_inflow:
            account.current_balance = F('current_balance') + tx.amount
        else:
            account.current_balance = F('current_balance') - tx.amount
        account.save(update_fields=['current_balance'])
        return tx


class CashRegisterSerializer(serializers.ModelSerializer):
    branch_name = serializers.CharField(source='branch.name', read_only=True)
    opened_by_name = serializers.CharField(source='opened_by.get_full_name', read_only=True)
    variance = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)

    class Meta:
        model = CashRegister
        fields = [
            'id', 'branch', 'branch_name', 'opened_by', 'opened_by_name', 'closed_by',
            'opening_balance', 'expected_closing_balance', 'counted_closing_balance',
            'status', 'variance', 'opened_at', 'closed_at',
        ]
        read_only_fields = ['branch', 'opened_by', 'closed_by', 'status', 'opened_at', 'closed_at']

    def create(self, validated_data):
        request = self.context['request']
        validated_data.pop('branch', None)
        return CashRegister.objects.create(opened_by=request.user, branch=request.user.branch, **validated_data)


class CloseCashRegisterSerializer(serializers.Serializer):
    counted_closing_balance = serializers.DecimalField(max_digits=14, decimal_places=2)

    def save(self, **kwargs):
        register = self.context['register']
        request = self.context['request']
        register.counted_closing_balance = self.validated_data['counted_closing_balance']
        register.status = CashRegister.Status.CLOSED
        register.closed_by = request.user
        from django.utils import timezone
        register.closed_at = timezone.now()
        register.save(update_fields=['counted_closing_balance', 'status', 'closed_by', 'closed_at'])
        return register


class ExpenseCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ExpenseCategory
        fields = ['id', 'name']


class ExpenseSerializer(BranchAutoAssignSerializerMixin, serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)
    branch_name = serializers.CharField(source='branch.name', read_only=True)

    class Meta:
        model = Expense
        fields = [
            'id', 'branch', 'branch_name', 'category', 'category_name', 'amount',
            'paid_from', 'bank_account', 'description', 'expense_date',
            'created_by', 'created_at',
        ]
        read_only_fields = ['expense_date', 'created_by', 'created_at']
        extra_kwargs = {'branch': {'required': False}}

    def create(self, validated_data):
        request = self.context['request']
        return Expense.objects.create(created_by=request.user, **validated_data)
