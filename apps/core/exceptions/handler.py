"""Format unique des erreurs API : {success, code, message}."""

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from apps.iam.exceptions import AuthAPIError


def api_exception_handler(exc, context):
    """Handler DRF (settings EXCEPTION_HANDLER). AuthAPIError en premier (401/403 métier)."""
    if isinstance(exc, AuthAPIError):
        body = {"success": False, "code": exc.code, "message": exc.message}
        extra = getattr(exc, "extra", None) or {}
        body.update(extra)
        return Response(body, status=exc.status_code)

    response = drf_exception_handler(exc, context)  # ValidationError, AuthenticationFailed, …
    if response is None:
        return Response(
            {
                "success": False,
                "code": "INTERNAL_ERROR",
                "message": "Une erreur interne est survenue.",
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    code = "ERROR"
    message = "Requête invalide."
    data = response.data
    if isinstance(data, dict):
        if "detail" in data:
            message = str(data["detail"])
            code = getattr(data["detail"], "code", "ERROR")
            if hasattr(code, "upper"):
                code = str(code).upper()
        elif data:
            message = "Données invalides."
            code = "VALIDATION_ERROR"  # serializers login / refresh

    response.data = {
        "success": False,
        "code": code,
        "message": message,
        "errors": data if isinstance(data, dict) and "detail" not in data else None,
    }
    return response
