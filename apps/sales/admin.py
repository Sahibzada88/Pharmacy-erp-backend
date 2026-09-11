from django.contrib import admin
from .models import Sale, SaleItem, SalePayment, SaleReturn


class SaleItemInline(admin.TabularInline):
    model = SaleItem
    extra = 0


class SalePaymentInline(admin.TabularInline):
    model = SalePayment
    extra = 0


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ('invoice_number', 'branch', 'cashier', 'total_amount', 'status', 'created_at')
    list_filter = ('branch', 'status', 'cashier')
    search_fields = ('invoice_number',)
    inlines = [SaleItemInline, SalePaymentInline]
    date_hierarchy = 'created_at'


@admin.register(SaleReturn)
class SaleReturnAdmin(admin.ModelAdmin):
    list_display = ('sale', 'quantity', 'refund_amount', 'branch', 'created_at')
    list_filter = ('branch',)
