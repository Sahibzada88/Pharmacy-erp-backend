from django.contrib.auth import get_user_model
from rest_framework import generics, permissions, status, filters
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView
from django_filters.rest_framework import DjangoFilterBackend

from .serializers import (
    CustomTokenObtainPairSerializer, UserSerializer,
    CreateStaffSerializer, ChangePasswordSerializer,
)
from .permissions import IsOwnerOrManager

User = get_user_model()


class LoginView(TokenObtainPairView):
    """POST username & password -> access, refresh, role-aware user payload."""
    serializer_class = CustomTokenObtainPairSerializer


class MeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)


class StaffListCreateView(generics.ListCreateAPIView):
    """
    Owner: sees/creates staff across all branches.
    Manager: sees/creates staff (cashier/accountant/pharmacist) for their own branch only.
    """
    permission_classes = [IsOwnerOrManager]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['role', 'branch', 'is_active_staff']
    search_fields = ['username', 'first_name', 'last_name', 'email']

    def get_queryset(self):
        user = self.request.user
        qs = User.objects.exclude(role=User.Role.OWNER).select_related('branch')
        if user.is_owner:
            return qs
        return qs.filter(branch_id=user.branch_id)

    def get_serializer_class(self):
        return CreateStaffSerializer if self.request.method == 'POST' else UserSerializer

    def perform_create(self, serializer):
        user = self.request.user
        if user.is_manager:
            serializer.save(branch=user.branch)
        else:
            serializer.save()


class StaffDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsOwnerOrManager]
    serializer_class = UserSerializer

    def get_queryset(self):
        user = self.request.user
        qs = User.objects.exclude(role=User.Role.OWNER)
        if user.is_owner:
            return qs
        return qs.filter(branch_id=user.branch_id)


class ChangePasswordView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = request.user
        if not user.check_password(serializer.validated_data['old_password']):
            return Response({'detail': 'Old password is incorrect.'}, status=status.HTTP_400_BAD_REQUEST)
        user.set_password(serializer.validated_data['new_password'])
        user.save()
        return Response({'detail': 'Password updated successfully.'})
