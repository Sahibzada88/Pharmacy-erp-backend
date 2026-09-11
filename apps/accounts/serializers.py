from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

User = get_user_model()


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Adds role/branch/name claims into the JWT so the frontend can route
    the correct dashboard (owner/cashier/accountant/pharmacist/manager)
    without an extra API call."""

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['role'] = user.role
        token['branch_id'] = user.branch_id
        token['full_name'] = user.get_full_name() or user.username
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        data['user'] = UserSerializer(self.user).data
        return data


class UserSerializer(serializers.ModelSerializer):
    branch_name = serializers.CharField(source='branch.name', read_only=True, default=None)

    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name',
            'role', 'branch', 'branch_name', 'phone', 'cnic',
            'is_active_staff', 'date_joined',
        ]
        read_only_fields = ['id', 'date_joined']


class CreateStaffSerializer(serializers.ModelSerializer):
    """Used by OWNER (or MANAGER for their own branch) to create staff accounts."""
    password = serializers.CharField(write_only=True, validators=[validate_password])

    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name', 'password',
            'role', 'branch', 'phone', 'cnic',
        ]

    def validate_role(self, value):
        if value == User.Role.OWNER:
            raise serializers.ValidationError("Cannot create another OWNER account via this endpoint.")
        return value

    def create(self, validated_data):
        password = validated_data.pop('password')
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True, validators=[validate_password])
