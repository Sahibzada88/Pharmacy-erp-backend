from django.contrib import admin
from .models import Customer, LoyaltyTransaction, CustomerNote


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('name', 'phone', 'home_branch', 'loyalty_points', 'is_active')
    search_fields = ('name', 'phone', 'email')
    list_filter = ('home_branch', 'is_active')


@admin.register(LoyaltyTransaction)
class LoyaltyTransactionAdmin(admin.ModelAdmin):
    list_display = ('customer', 'tx_type', 'points', 'created_at')
    list_filter = ('tx_type',)


@admin.register(CustomerNote)
class CustomerNoteAdmin(admin.ModelAdmin):
    list_display = ('customer', 'author', 'created_at')
