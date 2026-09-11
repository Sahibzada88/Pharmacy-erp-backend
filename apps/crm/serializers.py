from rest_framework import serializers
from .models import Customer, LoyaltyTransaction, CustomerNote


class CustomerSerializer(serializers.ModelSerializer):
    home_branch_name = serializers.CharField(source='home_branch.name', read_only=True, default=None)
    lifetime_spend = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)

    class Meta:
        model = Customer
        fields = [
            'id', 'name', 'phone', 'email', 'address', 'home_branch', 'home_branch_name',
            'loyalty_points', 'is_active', 'lifetime_spend', 'created_at',
        ]


class LoyaltyTransactionSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source='customer.name', read_only=True)

    class Meta:
        model = LoyaltyTransaction
        fields = ['id', 'customer', 'customer_name', 'sale', 'tx_type', 'points', 'note', 'created_at']


class CustomerNoteSerializer(serializers.ModelSerializer):
    author_name = serializers.CharField(source='author.get_full_name', read_only=True)

    class Meta:
        model = CustomerNote
        fields = ['id', 'customer', 'author', 'author_name', 'note', 'created_at']
        read_only_fields = ['author', 'created_at']

    def create(self, validated_data):
        request = self.context['request']
        return CustomerNote.objects.create(author=request.user, **validated_data)
