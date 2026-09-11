"""
Shared mixin: automatically scopes queryset to the requesting user's branch,
unless the user is OWNER (who sees all branches, chain-wide).

Any ViewSet whose model has a `branch` FK should inherit BranchScopedQuerysetMixin.
"""


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

    def perform_create(self, serializer):
        user = self.request.user
        extra = {}
        if not user.is_owner and self.branch_field == 'branch_id':
            extra['branch_id'] = user.branch_id
        serializer.save(**extra)
