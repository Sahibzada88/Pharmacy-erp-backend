from django.urls import path
from . import views

urlpatterns = [
    # Owner home dashboard
    path('owner-dashboard/', views.OwnerDashboardView.as_view(), name='analytics-owner-dashboard'),

    # Sales analytics
    path('sales/summary/', views.SalesSummaryView.as_view(), name='analytics-sales-summary'),
    path('sales/daily-trend/', views.DailySalesTrendView.as_view(), name='analytics-sales-trend'),
    path('sales/top-medicines/', views.TopSellingMedicinesView.as_view(), name='analytics-top-medicines'),
    path('sales/cashier-performance/', views.CashierPerformanceView.as_view(), name='analytics-cashier-performance'),
    path('sales/payment-methods/', views.PaymentMethodBreakdownView.as_view(), name='analytics-payment-methods'),

    # Inventory analytics
    path('inventory/stock-valuation/', views.StockValuationView.as_view(), name='analytics-stock-valuation'),
    path('inventory/stock-valuation-by-branch/', views.StockValuationByBranchView.as_view(), name='analytics-stock-valuation-by-branch'),
    path('inventory/expiry-report/', views.ExpiryReportView.as_view(), name='analytics-expiry-report'),
    path('inventory/low-stock/', views.LowStockReportView.as_view(), name='analytics-low-stock'),

    # Finance analytics
    path('finance/bank-balance/', views.BankBalanceSummaryView.as_view(), name='analytics-bank-balance'),
    path('finance/cash-position/', views.CashPositionView.as_view(), name='analytics-cash-position'),
    path('finance/expense-breakdown/', views.ExpenseBreakdownView.as_view(), name='analytics-expense-breakdown'),
    path('finance/profit-and-loss/', views.ProfitAndLossView.as_view(), name='analytics-profit-and-loss'),

    # Supplier analytics
    path('suppliers/dues/', views.SupplierDuesView.as_view(), name='analytics-supplier-dues'),
    path('suppliers/payment-trend/', views.SupplierPaymentTrendView.as_view(), name='analytics-supplier-payment-trend'),
]
