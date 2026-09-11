from rest_framework.routers import DefaultRouter
from .views import (
    BankAccountViewSet, BankTransactionViewSet, CashRegisterViewSet,
    ExpenseCategoryViewSet, ExpenseViewSet,
)

router = DefaultRouter()
router.register('bank-accounts', BankAccountViewSet, basename='bank-account')
router.register('bank-transactions', BankTransactionViewSet, basename='bank-transaction')
router.register('cash-registers', CashRegisterViewSet, basename='cash-register')
router.register('expense-categories', ExpenseCategoryViewSet, basename='expense-category')
router.register('expenses', ExpenseViewSet, basename='expense')

urlpatterns = router.urls
