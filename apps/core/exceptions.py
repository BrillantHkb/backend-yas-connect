from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler


def api_exception_handler(exc, context):
    response = drf_exception_handler(exc, context)
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
            code = "VALIDATION_ERROR"

    response.data = {
        "success": False,
        "code": code,
        "message": message,
        "errors": data if isinstance(data, dict) and "detail" not in data else None,
    }
    return response
