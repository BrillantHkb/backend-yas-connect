"""GET publics dropdowns inscription (slice ANNUAIRE-A)."""

from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.annuaire.models import Segment
from apps.iam.models import Region


class DirectoryRegionsView(APIView):
    authentication_classes = []  # dropdown inscription : public
    permission_classes = [AllowAny]

    @extend_schema(tags=["Directory"], auth=[], description="Régions TG (id, code, name).")
    def get(self, request):
        rows = [
            {"id": str(r.id), "code": r.code, "name": r.name}
            for r in Region.objects.order_by("code")
        ]
        return Response({"success": True, "data": rows})


class DirectorySegmentsView(APIView):
    authentication_classes = []  # dropdown inscription : public
    permission_classes = [AllowAny]

    @extend_schema(tags=["Directory"], auth=[], description="Segments org actifs (id, code, name).")
    def get(self, request):
        rows = [
            {"id": str(s.id), "code": s.code, "name": s.name}
            for s in Segment.objects.filter(is_active=True).order_by("code")
        ]
        return Response({"success": True, "data": rows})
