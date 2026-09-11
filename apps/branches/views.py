from rest_framework import viewsets, permissions
from .models import Branch
from .serializers import BranchSerializer
from apps.accounts.permissions import IsOwner


class BranchViewSet(viewsets.ModelViewSet):
    """
    Only OWNER can create/update/delete branches (opening/closing pharmacy locations).
    Any authenticated staff can list branches (read-only) so dropdowns work in the frontend,
    but non-owners only see their own branch.
    """
    queryset = Branch.objects.all()
    serializer_class = BranchSerializer

    def get_permissions(self):
        if self.action in ('create', 'update', 'partial_update', 'destroy'):
            return [IsOwner()]
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        user = self.request.user
        if user.is_owner:
            return Branch.objects.all()
        return Branch.objects.filter(id=user.branch_id)
