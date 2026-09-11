"""
Analytics endpoints. Every endpoint calls a Postgres stored procedure via
apps.analytics.db.call_function(_one) for speed, instead of heavy Django ORM
aggregation. Access is scoped by role:

  - OWNER      : full chain-wide analytics, any branch, all modules.
  - MANAGER    : full analytics for their own branch only.
  - ACCOUNTANT : finance-focused analytics (sales totals, bank, supplier dues,
                 expenses, P&L) chain-wide or per branch — NOT staff performance.
  - CASHIER    : none of these (POS-focused); can see their own till summary
                 via finance app (CashRegister), not full analytics.
  - PHARMACIST : inventory-focused analytics only (stock, expiry).
"""
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from .db import call_function, call_function_one
from .utils import resolve_branch_id, resolve_date_range
from apps.accounts.permissions import HasAnyRole


class OwnerDashboardView(APIView):
    """One-shot KPI summary for the owner's home dashboard."""
    permission_classes = [HasAnyRole('OWNER', 'MANAGER', 'ACCOUNTANT')]

    def get(self, request):
        branch_id = resolve_branch_id(request)
        date_from, date_to = resolve_date_range(request)
        summary = call_function_one('fn_owner_dashboard_summary', (branch_id, date_from, date_to))
        return Response({
            'branch_id': branch_id,
            'date_from': date_from,
            'date_to': date_to,
            'summary': summary,
        })


class SalesSummaryView(APIView):
    permission_classes = [HasAnyRole('OWNER', 'MANAGER', 'ACCOUNTANT')]

    def get(self, request):
        branch_id = resolve_branch_id(request)
        date_from, date_to = resolve_date_range(request)
        summary = call_function_one('fn_sales_summary', (branch_id, date_from, date_to))
        return Response({'branch_id': branch_id, 'date_from': date_from, 'date_to': date_to, 'summary': summary})


class DailySalesTrendView(APIView):
    permission_classes = [HasAnyRole('OWNER', 'MANAGER', 'ACCOUNTANT')]

    def get(self, request):
        branch_id = resolve_branch_id(request)
        date_from, date_to = resolve_date_range(request)
        trend = call_function('fn_daily_sales_trend', (branch_id, date_from, date_to))
        return Response({'branch_id': branch_id, 'date_from': date_from, 'date_to': date_to, 'trend': trend})


class TopSellingMedicinesView(APIView):
    permission_classes = [HasAnyRole('OWNER', 'MANAGER', 'ACCOUNTANT', 'PHARMACIST')]

    def get(self, request):
        branch_id = resolve_branch_id(request)
        date_from, date_to = resolve_date_range(request)
        limit = int(request.query_params.get('limit', 10))
        data = call_function('fn_top_selling_medicines', (branch_id, date_from, date_to, limit))
        return Response({'branch_id': branch_id, 'date_from': date_from, 'date_to': date_to, 'results': data})


class CashierPerformanceView(APIView):
    """Owner/manager oversight of cashier sales performance — not for accountant."""
    permission_classes = [HasAnyRole('OWNER', 'MANAGER')]

    def get(self, request):
        branch_id = resolve_branch_id(request) if request.user.is_owner else request.user.branch_id
        date_from, date_to = resolve_date_range(request)
        data = call_function('fn_cashier_performance', (branch_id, date_from, date_to))
        return Response({'branch_id': branch_id, 'date_from': date_from, 'date_to': date_to, 'results': data})


class PaymentMethodBreakdownView(APIView):
    permission_classes = [HasAnyRole('OWNER', 'MANAGER', 'ACCOUNTANT')]

    def get(self, request):
        branch_id = resolve_branch_id(request)
        date_from, date_to = resolve_date_range(request)
        data = call_function('fn_payment_method_breakdown', (branch_id, date_from, date_to))
        return Response({'branch_id': branch_id, 'date_from': date_from, 'date_to': date_to, 'results': data})


# ---------------------------------------------------------------------------
# Inventory analytics
# ---------------------------------------------------------------------------

class StockValuationView(APIView):
    """'kitna stock hai, kitne paise ka hai' — chain-wide or per-branch."""
    permission_classes = [HasAnyRole('OWNER', 'MANAGER', 'ACCOUNTANT', 'PHARMACIST')]

    def get(self, request):
        branch_id = resolve_branch_id(request) if not request.user.is_owner else resolve_branch_id(request)
        if not request.user.is_owner and not request.user.is_accountant:
            branch_id = request.user.branch_id
        summary = call_function_one('fn_stock_valuation', (branch_id,))
        return Response({'branch_id': branch_id, 'summary': summary})


class StockValuationByBranchView(APIView):
    """Owner-only: compare stock value across all branches side by side."""
    permission_classes = [HasAnyRole('OWNER')]

    def get(self, request):
        data = call_function('fn_stock_valuation_by_branch', ())
        return Response({'results': data})


class ExpiryReportView(APIView):
    permission_classes = [HasAnyRole('OWNER', 'MANAGER', 'PHARMACIST')]

    def get(self, request):
        branch_id = resolve_branch_id(request) if request.user.is_owner else request.user.branch_id
        days = int(request.query_params.get('days', 60))
        data = call_function('fn_expiry_report', (branch_id, days))
        return Response({'branch_id': branch_id, 'days': days, 'results': data})


class LowStockReportView(APIView):
    permission_classes = [HasAnyRole('OWNER', 'MANAGER', 'PHARMACIST')]

    def get(self, request):
        branch_id = resolve_branch_id(request) if request.user.is_owner else request.user.branch_id
        data = call_function('fn_low_stock_report', (branch_id,))
        return Response({'branch_id': branch_id, 'results': data})


# ---------------------------------------------------------------------------
# Finance analytics
# ---------------------------------------------------------------------------

class BankBalanceSummaryView(APIView):
    permission_classes = [HasAnyRole('OWNER', 'ACCOUNTANT')]

    def get(self, request):
        branch_id = resolve_branch_id(request)
        data = call_function('fn_bank_balance_summary', (branch_id,))
        total = sum(row['current_balance'] for row in data)
        return Response({'branch_id': branch_id, 'total_balance': total, 'accounts': data})


class CashPositionView(APIView):
    permission_classes = [HasAnyRole('OWNER', 'MANAGER', 'ACCOUNTANT')]

    def get(self, request):
        branch_id = resolve_branch_id(request) if request.user.is_owner or request.user.is_accountant else request.user.branch_id
        date_from, date_to = resolve_date_range(request)
        data = call_function('fn_cash_position', (branch_id, date_from, date_to))
        return Response({'date_from': date_from, 'date_to': date_to, 'results': data})


class ExpenseBreakdownView(APIView):
    permission_classes = [HasAnyRole('OWNER', 'MANAGER', 'ACCOUNTANT')]

    def get(self, request):
        branch_id = resolve_branch_id(request) if request.user.is_owner or request.user.is_accountant else request.user.branch_id
        date_from, date_to = resolve_date_range(request)
        data = call_function('fn_expense_breakdown', (branch_id, date_from, date_to))
        return Response({'date_from': date_from, 'date_to': date_to, 'results': data})


class ProfitAndLossView(APIView):
    permission_classes = [HasAnyRole('OWNER', 'ACCOUNTANT')]

    def get(self, request):
        branch_id = resolve_branch_id(request)
        date_from, date_to = resolve_date_range(request)
        summary = call_function_one('fn_profit_and_loss', (branch_id, date_from, date_to))
        return Response({'branch_id': branch_id, 'date_from': date_from, 'date_to': date_to, 'summary': summary})


# ---------------------------------------------------------------------------
# Supplier analytics
# ---------------------------------------------------------------------------

class SupplierDuesView(APIView):
    """'kitne supplier ko dene hain' — accounts payable by supplier."""
    permission_classes = [HasAnyRole('OWNER', 'MANAGER', 'ACCOUNTANT')]

    def get(self, request):
        branch_id = resolve_branch_id(request) if request.user.is_owner or request.user.is_accountant else request.user.branch_id
        data = call_function('fn_supplier_dues', (branch_id,))
        total_due = sum(row['balance_due'] for row in data)
        return Response({'branch_id': branch_id, 'total_due': total_due, 'suppliers': data})


class SupplierPaymentTrendView(APIView):
    permission_classes = [HasAnyRole('OWNER', 'ACCOUNTANT')]

    def get(self, request):
        branch_id = resolve_branch_id(request)
        date_from, date_to = resolve_date_range(request)
        data = call_function('fn_supplier_payment_trend', (branch_id, date_from, date_to))
        return Response({'date_from': date_from, 'date_to': date_to, 'results': data})
