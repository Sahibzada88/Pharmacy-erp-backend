from django.contrib import admin
from .models import Branch


@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'city', 'is_active', 'opened_on')
    search_fields = ('name', 'code', 'city')
    list_filter = ('is_active', 'city')
