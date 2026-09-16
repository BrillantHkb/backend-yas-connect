"""MESSAGERIE-F : signalement de message + modération admin (MSG-93…98)."""

from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.messaging.serializers.reports import ReportCreateSerializer, ReportReviewSerializer
from apps.messaging.services import report_service


class MessageReportView(APIView):
    required_permission = "messaging.report.create"

    @extend_schema(
        tags=["Messagerie"],
        request=ReportCreateSerializer,
        responses={201: OpenApiResponse(), 429: OpenApiResponse(description="REPORT_RATE_LIMITED")},
    )
    def post(self, request, pk):
        ser = ReportCreateSerializer(data=request.data or {})
        ser.is_valid(raise_exception=True)
        data = report_service.create_report(
            user=request.user, message_id=pk, reason=ser.validated_data["reason"]
        )
        return Response({"success": True, "data": data}, status=201)


class AdminReportedMessagesView(APIView):
    required_permission = "messaging.report.review"

    @extend_schema(
        tags=["Messagerie (admin)"],
        parameters=[OpenApiParameter("status", str, OpenApiParameter.QUERY, required=False)],
        responses={200: OpenApiResponse()},
    )
    def get(self, request):
        data = report_service.list_reports(status=request.query_params.get("status"))
        return Response({"success": True, "data": data})


class AdminReportedMessageDetailView(APIView):
    required_permission = "messaging.report.review"

    @extend_schema(
        tags=["Messagerie (admin)"],
        request=ReportReviewSerializer,
        responses={200: OpenApiResponse()},
    )
    def patch(self, request, pk):
        ser = ReportReviewSerializer(data=request.data or {})
        ser.is_valid(raise_exception=True)
        data = report_service.review_report(
            user=request.user,
            report_id=pk,
            status=ser.validated_data["status"],
            note=ser.validated_data["note"],
        )
        return Response({"success": True, "data": data})
