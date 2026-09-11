from django.contrib import admin
from .models import Category, Manufacturer, Medicine, Batch, StockMovement


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)


@admin.register(Manufacturer)
class ManufacturerAdmin(admin.ModelAdmin):
    list_display = ('name', 'country')
    search_fields = ('name',)


@admin.register(Medicine)
class MedicineAdmin(admin.ModelAdmin):
    list_display = ('name', 'sku', 'category', 'manufacturer', 'unit_type', 'reorder_level', 'is_active')
    search_fields = ('name', 'generic_name', 'sku', 'barcode')
    list_filter = ('category', 'unit_type', 'is_active', 'requires_prescription')


@admin.register(Batch)
class BatchAdmin(admin.ModelAdmin):
    list_display = ('medicine', 'branch', 'batch_number', 'quantity_remaining', 'sale_price', 'expiry_date', 'is_active')
    list_filter = ('branch', 'is_active')
    search_fields = ('medicine__name', 'batch_number')
    date_hierarchy = 'expiry_date'


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ('batch', 'branch', 'movement_type', 'quantity', 'created_by', 'created_at')
    list_filter = ('movement_type', 'branch')
    search_fields = ('batch__medicine__name', 'reference')
