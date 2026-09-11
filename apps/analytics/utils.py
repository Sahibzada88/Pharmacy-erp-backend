from datetime import date, timedelta
from rest_framework.exceptions import ValidationError


def resolve_branch_id(request):
    """
    OWNER: can view chain-wide (branch=None) or a specific branch via ?branch=<id>.
    ACCOUNTANT: chain-wide financial visibility (needed for consolidated books) by default,
                or a specific branch via ?branch=<id>.
    Everyone else (manager/cashier/pharmacist): locked to their own branch only.
    """
    user = request.user
    branch_param = request.query_params.get('branch')

    if user.is_owner or user.is_accountant:
        return int(branch_param) if branch_param else None
    return user.branch_id


def resolve_date_range(request, default_days=30):
    date_from = request.query_params.get('date_from')
    date_to = request.query_params.get('date_to')

    if date_to:
        date_to = date.fromisoformat(date_to)
    else:
        date_to = date.today()

    if date_from:
        date_from = date.fromisoformat(date_from)
    else:
        date_from = date_to - timedelta(days=default_days)

    if date_from > date_to:
        raise ValidationError("date_from must be before date_to.")

    return date_from, date_to
