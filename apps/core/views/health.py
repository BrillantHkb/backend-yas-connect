"""GET /health — public (jour 0)."""

from django.db import connection
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


class HealthView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Santé"],
        auth=[],
        responses={
            200: {
                "type": "object",
                "properties": {
                    "success": {"type": "boolean"},
                    "data": {
                        "type": "object",
                        "properties": {
                            "status": {"type": "string"},
                            "db": {"type": "boolean"},
                        },
                    },
                },
            }
        },
        description="Liveness. `db=true` si SELECT 1 Postgres OK.",
    )
    def get(self, request):
        db_ok = True
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
        except Exception:
            db_ok = False
        status = 200 if db_ok else 503
        return Response(
            {"success": True, "data": {"status": "ok" if db_ok else "degraded", "db": db_ok}},
            status=status,
        )
