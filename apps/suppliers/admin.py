from django.contrib import admin
from .models import Supplier, PurchaseOrder, PurchaseOrderItem, SupplierPayment


class PurchaseOrderItemInline(admin.TabularInline):
    model = PurchaseOrderItem
    extra = 1


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ('name', 'contact_person', 'phone', 'is_active')
    search_fields = ('name', 'contact_person', 'phone')


@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
    list_display = ('po_number', 'supplier', 'branch', 'status', 'order_date', 'received_date')
    list_filter = ('status', 'branch', 'supplier')
    search_fields = ('po_number',)
    inlines = [PurchaseOrderItemInline]


@admin.register(SupplierPayment)
class SupplierPaymentAdmin(admin.ModelAdmin):
    list_display = ('supplier', 'branch', 'amount', 'method', 'paid_on')
    list_filter = ('method', 'branch', 'supplier')
