from rest_framework import viewsets, permissions, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend

from .models import BankAccount, BankTransaction, CashRegister, ExpenseCategory, Expense
from .serializers import (
    BankAccountSerializer, BankTransactionSerializer, CashRegisterSerializer,
    CloseCashRegisterSerializer, ExpenseCategorySerializer, ExpenseSerializer,
)
from apps.accounts.permissions import IsOwner, IsOwnerOrAccountant
from apps.accounts.mixins import BranchScopedQuerysetMixin


class BankAccountViewSet(viewsets.ModelViewSet):
    """Bank accounts are chain-wide/head-office visible to owner & accountant;
    branch-specific accounts are still visible to that branch's staff."""
    queryset = BankAccount.objects.all()
    serializer_class = BankAccountSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['branch', 'is_active']

    def get_permissions(self):
        if self.action in ('create', 'update', 'partial_update', 'destroy'):
            return [IsOwner()]
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        user = self.request.user
        if user.is_owner or user.is_accountant:
            return BankAccount.objects.all()
        return BankAccount.objects.filter(branch_id=user.branch_id)


class BankTransactionViewSet(viewsets.ModelViewSet):
    queryset = BankTransaction.objects.select_related('bank_account', 'branch').all()
    serializer_class = BankTransactionSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['bank_account', 'branch', 'tx_type']
    ordering_fields = ['created_at']

    def get_permissions(self):
        if self.action in ('create', 'update', 'partial_update', 'destroy'):
            return [IsOwnerOrAccountant()]
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        user = self.request.user
        qs = BankTransaction.objects.select_related('bank_account', 'branch').all()
        if user.is_owner or user.is_accountant:
            return qs
        return qs.filter(branch_id=user.branch_id)


class CashRegisterViewSet(BranchScopedQuerysetMixin, viewsets.ModelViewSet):
    """Cashiers open/close their own daily cash drawer; owner/accountant view all."""
    queryset = CashRegister.objects.select_related('branch', 'opened_by').all()
    serializer_class = CashRegisterSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['branch', 'status']

    def get_permissions(self):
        return [permissions.IsAuthenticated()]

    @action(detail=True, methods=['post'])
    def close(self, request, pk=None):
        register = self.get_object()
        serializer = CloseCashRegisterSerializer(
            data=request.data, context={'register': register, 'request': request}
        )
        serializer.is_valid(raise_exception=True)
        register = serializer.save()
        return Response(CashRegisterSerializer(register).data)


class ExpenseCategoryViewSet(viewsets.ModelViewSet):
    queryset = ExpenseCategory.objects.all()
    serializer_class = ExpenseCategorySerializer

    def get_permissions(self):
        if self.action in ('create', 'update', 'partial_update', 'destroy'):
            return [IsOwnerOrAccountant()]
        return [permissions.IsAuthenticated()]


class ExpenseViewSet(BranchScopedQuerysetMixin, viewsets.ModelViewSet):
    queryset = Expense.objects.select_related('branch', 'category').all()
    serializer_class = ExpenseSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['branch', 'category', 'paid_from']
    ordering_fields = ['expense_date']

    def get_permissions(self):
        if self.action in ('create', 'update', 'partial_update', 'destroy'):
            return [IsOwnerOrAccountant()]
        return [permissions.IsAuthenticated()]
