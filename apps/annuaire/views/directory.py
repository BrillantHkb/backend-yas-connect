"""GET publics dropdowns inscription (ANNUAIRE-A) + segment-types / parent_id (delta jour 17)."""

import uuid

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.annuaire.models import Segment, SegmentType
from apps.iam.exceptions import AuthAPIError
from apps.iam.models import Region

MSG_PARENT_ID = "Paramètre parent_id invalide."


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


class DirectorySegmentTypesView(APIView):
    authentication_classes = []  # dropdown inscription : public
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Directory"],
        auth=[],
        description="Types d’unité actifs (id, code, name, level). Tri level, code.",
    )
    def get(self, request):
        rows = [
            {"id": str(t.id), "code": t.code, "name": t.name, "level": t.level}
            for t in SegmentType.objects.filter(is_active=True).order_by("level", "code")
        ]
        return Response({"success": True, "data": rows})


class DirectorySegmentsView(APIView):
    authentication_classes = []  # dropdown inscription : public
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Directory"],
        auth=[],
        parameters=[
            OpenApiParameter(
                "parent_id",
                str,
                OpenApiParameter.QUERY,
                required=False,
                description="Omis = racines (parent_segment IS NULL). UUID invalide → 400.",
            ),
        ],
        description="Segments actifs (id, code, name, type_code, parent_id).",
    )
    def get(self, request):
        raw_parent = request.query_params.get("parent_id")
        qs = Segment.objects.filter(is_active=True).select_related("segment_type")
        if raw_parent is None:
            qs = qs.filter(parent_segment_id__isnull=True)
        else:
            try:
                parent_id = uuid.UUID(str(raw_parent))
            except (TypeError, ValueError) as exc:
                raise AuthAPIError(
                    400, "VALIDATION_ERROR", MSG_PARENT_ID, extra={"field": "parent_id"}
                ) from exc
            qs = qs.filter(parent_segment_id=parent_id)
        rows = [
            {
                "id": str(s.id),
                "code": s.code,
                "name": s.name,
                "type_code": s.segment_type.code if s.segment_type else None,
                "parent_id": str(s.parent_segment_id) if s.parent_segment_id else None,
            }
            for s in qs.order_by("code")
        ]
        return Response({"success": True, "data": rows})
