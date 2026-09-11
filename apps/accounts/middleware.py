class ActiveBranchMiddleware:
    """
    Reads an optional 'X-Branch-Id' header so an OWNER using a multi-branch
    dashboard can switch "active branch" context without changing JWT.
    Non-owner roles always operate within their own assigned branch, so the
    header is ignored for them (enforced again in mixins/views).
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.active_branch_id = request.headers.get('X-Branch-Id')
        return self.get_response(request)
