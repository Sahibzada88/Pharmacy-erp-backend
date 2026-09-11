from rest_framework import viewsets, permissions, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from django_filters.rest_framework import DjangoFilterBackend

from .models import Sale, SaleReturn
from .serializers import SaleSerializer, CheckoutSerializer, SaleReturnCreateSerializer
from apps.accounts.permissions import IsCashierOrAbove
from apps.accounts.mixins import BranchScopedQuerysetMixin


class SaleViewSet(BranchScopedQuerysetMixin, viewsets.ReadOnlyModelViewSet):
    """Read-only invoice history. Sale creation happens via CheckoutView (POS)."""
    queryset = Sale.objects.select_related('branch', 'cashier', 'customer').prefetch_related('items', 'payments').all()
    serializer_class = SaleSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['branch', 'cashier', 'status', 'customer']
    search_fields = ['invoice_number']
    ordering_fields = ['created_at', 'total_amount']


class CheckoutView(APIView):
    """
    POST /api/sales/checkout/
    Main POS endpoint used by the Cashier dashboard to complete a sale.
    Body: { items: [{medicine_id, quantity, discount_amount?, batch_id?}],
            payments: [{method, amount, bank_account?, reference_number?}],
            customer?, discount_amount?, tax_amount?, note? }
    """
    permission_classes = [IsCashierOrAbove]

    def post(self, request):
        serializer = CheckoutSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        sale = serializer.save()
        return Response(SaleSerializer(sale).data, status=status.HTTP_201_CREATED)


class SaleReturnView(APIView):
    """POST /api/sales/returns/ — process a customer return for a specific sale line item."""
    permission_classes = [IsCashierOrAbove]

    def post(self, request):
        serializer = SaleReturnCreateSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        sale_return = serializer.save()
        return Response({
            'detail': 'Return processed.',
            'refund_amount': sale_return.refund_amount,
            'sale': SaleSerializer(sale_return.sale).data,
        }, status=status.HTTP_201_CREATED)
