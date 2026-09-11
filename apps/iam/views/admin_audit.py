"""ADMIN-A : lecture audit_logs. JWT + HasPermission."""

from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.iam.services.admin_user_service import list_audit_logs


class AdminAuditLogListView(APIView):
    required_permission = "iam.audit.read"

    @extend_schema(
        tags=["Admin"],
        parameters=[
            OpenApiParameter("user_id", str, OpenApiParameter.QUERY, required=False),
            OpenApiParameter("entity_type", str, OpenApiParameter.QUERY, required=False),
            OpenApiParameter("entity_id", str, OpenApiParameter.QUERY, required=False),
            OpenApiParameter("module", str, OpenApiParameter.QUERY, required=False),
            OpenApiParameter("action", str, OpenApiParameter.QUERY, required=False),
            OpenApiParameter("success", bool, OpenApiParameter.QUERY, required=False),
            OpenApiParameter("from", str, OpenApiParameter.QUERY, required=False),
            OpenApiParameter("to", str, OpenApiParameter.QUERY, required=False),
            OpenApiParameter("limit", int, OpenApiParameter.QUERY, required=False),
            OpenApiParameter("offset", int, OpenApiParameter.QUERY, required=False),
        ],
        responses={200: OpenApiResponse(description="Audit paginé (sans hash)")},
    )
    def get(self, request):
        return Response({"success": True, "data": list_audit_logs(request=request)})
