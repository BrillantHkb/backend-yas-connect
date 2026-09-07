from django.db import connection
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


class HealthView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

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
