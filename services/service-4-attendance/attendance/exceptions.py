from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.views import exception_handler as drf_handler


class DomainError(APIException):
    """Erreur métier : renvoie {"error": <code>, "detail": <message>}."""
    status_code = status.HTTP_400_BAD_REQUEST

    def __init__(self, code, message, http_status=400):
        self.status_code = http_status
        self.error_code = code
        super().__init__(detail=message, code=code)


def exception_handler(exc, context):
    response = drf_handler(exc, context)
    if response is None:
        return None
    if isinstance(exc, DomainError):
        response.data = {"error": exc.error_code, "detail": str(exc.detail)}
    elif isinstance(response.data, dict) and "detail" in response.data:
        response.data = {"error": getattr(exc, "default_code", "error"), "detail": str(response.data["detail"])}
    else:
        response.data = {"error": "validation_error", "detail": response.data}
    return response
