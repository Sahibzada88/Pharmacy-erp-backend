from rest_framework.views import exception_handler


def custom_exception_handler(exc, context):
    """Wraps DRF's default handler to produce a consistent error envelope."""
    response = exception_handler(exc, context)

    if response is not None:
        response.data = {
            'success': False,
            'errors': response.data,
            'status_code': response.status_code,
        }
    return response
