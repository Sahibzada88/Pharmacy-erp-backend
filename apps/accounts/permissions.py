"""
Role-based permission classes shared across all apps.

Usage:
    permission_classes = [IsOwner]
    permission_classes = [IsOwnerOrManager]
    permission_classes = [IsOwnerOrAccountant]
    permission_classes = [HasAnyRole('OWNER', 'MANAGER', 'CASHIER')]
"""
from rest_framework.permissions import BasePermission


class IsOwner(BasePermission):
    message = "Only the owner can perform this action."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_owner)


class IsOwnerOrManager(BasePermission):
    message = "Only owner or branch manager can perform this action."

    def has_permission(self, request, view):
        u = request.user
        return bool(u and u.is_authenticated and (u.is_owner or u.is_manager))


class IsOwnerOrAccountant(BasePermission):
    message = "Only owner or accountant can perform this action."

    def has_permission(self, request, view):
        u = request.user
        return bool(u and u.is_authenticated and (u.is_owner or u.is_accountant))


class IsCashierOrAbove(BasePermission):
    """Cashier, manager, owner — used for POS sale creation."""
    message = "You do not have permission to operate the POS."

    def has_permission(self, request, view):
        u = request.user
        return bool(u and u.is_authenticated and u.role in ('CASHIER', 'MANAGER', 'OWNER'))


class IsPharmacistOrAbove(BasePermission):
    message = "Only pharmacist, manager or owner can perform this action."

    def has_permission(self, request, view):
        u = request.user
        return bool(u and u.is_authenticated and u.role in ('PHARMACIST', 'MANAGER', 'OWNER'))


def HasAnyRole(*roles):
    """Factory returning a permission class allowing only the given roles."""

    class _HasAnyRole(BasePermission):
        message = f"Requires one of roles: {', '.join(roles)}."

        def has_permission(self, request, view):
            u = request.user
            return bool(u and u.is_authenticated and u.role in roles)

    return _HasAnyRole


class IsSameBranchOrOwner(BasePermission):
    """
    Object-level: owner sees everything; other roles restricted to their own branch's data.
    Assumes the object has a `branch` attribute (directly or via `branch_id`).
    """
    message = "You can only access data for your own branch."

    def has_object_permission(self, request, view, obj):
        u = request.user
        if u.is_owner:
            return True
        obj_branch_id = getattr(obj, 'branch_id', None)
        return obj_branch_id is not None and obj_branch_id == u.branch_id
