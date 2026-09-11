from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ('username', 'get_full_name', 'role', 'branch', 'is_active_staff', 'is_active')
    list_filter = ('role', 'branch', 'is_active_staff', 'is_active')
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Pharmacy ERP', {'fields': ('role', 'branch', 'phone', 'cnic', 'is_active_staff')}),
    )
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ('Pharmacy ERP', {'fields': ('role', 'branch', 'phone', 'cnic')}),
    )
