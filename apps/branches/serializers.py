from rest_framework import serializers
from .models import Branch


class BranchSerializer(serializers.ModelSerializer):
    staff_count = serializers.IntegerField(source='staff.count', read_only=True)

    class Meta:
        model = Branch
        fields = [
            'id', 'name', 'code', 'address', 'city', 'phone',
            'license_number', 'is_active', 'opened_on',
            'staff_count', 'created_at', 'updated_at',
        ]
