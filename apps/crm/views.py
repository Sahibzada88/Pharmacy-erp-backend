from rest_framework import viewsets, permissions, filters
from django_filters.rest_framework import DjangoFilterBackend

from .models import Customer, LoyaltyTransaction, CustomerNote
from .serializers import CustomerSerializer, LoyaltyTransactionSerializer, CustomerNoteSerializer
from apps.accounts.permissions import IsCashierOrAbove


class CustomerViewSet(viewsets.ModelViewSet):
    """Customers are visible chain-wide (any cashier can look up a customer by phone)."""
    queryset = Customer.objects.select_related('home_branch').all()
    serializer_class = CustomerSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['home_branch', 'is_active']
    search_fields = ['name', 'phone', 'email']

    def get_permissions(self):
        if self.action in ('create', 'update', 'partial_update', 'destroy'):
            return [IsCashierOrAbove()]
        return [permissions.IsAuthenticated()]

    def perform_create(self, serializer):
        user = self.request.user
        if not user.is_owner and not serializer.validated_data.get('home_branch'):
            serializer.save(home_branch=user.branch)
        else:
            serializer.save()


class LoyaltyTransactionViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = LoyaltyTransaction.objects.select_related('customer').all()
    serializer_class = LoyaltyTransactionSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['customer', 'tx_type']


class CustomerNoteViewSet(viewsets.ModelViewSet):
    queryset = CustomerNote.objects.select_related('customer', 'author').all()
    serializer_class = CustomerNoteSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['customer']
    permission_classes = [IsCashierOrAbove]
