"""
Shared mixin: automatically scopes queryset to the requesting user's branch,
unless the user is OWNER (who sees all branches, chain-wide).

Any ViewSet whose model has a `branch` FK should inherit BranchScopedQuerysetMixin.
"""
from rest_framework import serializers


class BranchScopedQuerysetMixin:
    branch_field = 'branch_id'

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if not user.is_authenticated:
            return qs.none()
        if user.is_owner:
            # Owner can optionally filter by ?branch=<id>
            branch_param = self.request.query_params.get('branch')
            if branch_param:
                return qs.filter(**{self.branch_field: branch_param})
            return qs
        return qs.filter(**{self.branch_field: user.branch_id})

    # NOTE: branch assignment on create is handled at the serializer level
    # (see BranchAutoAssignSerializerMixin below, or a custom .create() on the
    # serializer itself, e.g. CashRegisterSerializer). Do NOT also inject
    # branch/branch_id here — passing both `branch` and `branch_id` to
    # Model.objects.create() in the same call raises a TypeError.


class BranchAutoAssignSerializerMixin:
    """
    Makes the serializer's `branch` field optional in the request body:
      - Non-owner users (manager/cashier/accountant/pharmacist) get their own
        branch auto-assigned, so they never need to send `branch` at all.
      - OWNER must explicitly specify `branch` (since they operate chain-wide);
        a clear validation error is raised instead of a 400 "field required"
        or, worse, a database NOT NULL crash.

    Add this mixin FIRST in the serializer's base classes, and add
        extra_kwargs = {'branch': {'required': False}}
    to that serializer's Meta so DRF doesn't reject a missing `branch` before
    this validate() method gets a chance to fill it in.
    """

    def validate(self, attrs):
        attrs = super().validate(attrs)
        # Only auto-assign/require branch on CREATE. On update/PATCH, `self.instance`
        # is already set and `branch` may legitimately be absent from attrs simply
        # because the client didn't touch that field in this request.
        if self.instance is not None:
            return attrs

        request = self.context.get('request')
        if request is not None and getattr(request, 'user', None) and request.user.is_authenticated:
            user = request.user
            if not attrs.get('branch'):
                if user.is_owner:
                    raise serializers.ValidationError({
                        'branch': 'Owner must specify a branch explicitly when creating this record.'
                    })
                attrs['branch'] = user.branch
        return attrs
