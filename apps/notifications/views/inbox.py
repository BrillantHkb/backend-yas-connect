"""NOTIF-A : GET inbox, unread-count, mark-read, read-all (NOTIF-01…04)."""

from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.notifications.services.notification_service import (
    list_inbox,
    mark_all_read,
    mark_read,
    unread_count,
)


def _parse_bool(raw) -> bool:
    return str(raw).strip().lower() in ("1", "true", "yes")


class NotificationListView(APIView):
    required_permission = "notifications.inbox.read"

    @extend_schema(
        tags=["Notifications"],
        parameters=[
            OpenApiParameter("before", str, OpenApiParameter.QUERY, required=False),
            OpenApiParameter("limit", int, OpenApiParameter.QUERY, required=False),
            OpenApiParameter("unread_only", bool, OpenApiParameter.QUERY, required=False),
        ],
        responses={200: OpenApiResponse(description="Inbox paginée (keyset)")},
    )
    def get(self, request):
        params = request.query_params
        data = list_inbox(
            user=request.user,
            before=params.get("before"),
            limit=params.get("limit"),
            unread_only=_parse_bool(params.get("unread_only")),
        )
        return Response({"success": True, "data": data})


class UnreadCountView(APIView):
    required_permission = "notifications.inbox.read"

    @extend_schema(tags=["Notifications"], responses={200: OpenApiResponse(description="Badge")})
    def get(self, request):
        return Response({"success": True, "data": {"count": unread_count(user=request.user)}})


class NotificationReadView(APIView):
    required_permission = "notifications.inbox.update"

    @extend_schema(
        tags=["Notifications"], responses={204: OpenApiResponse(), 404: OpenApiResponse()}
    )
    def post(self, request, pk):
        mark_read(user=request.user, pk=pk)
        return Response(status=204)


class ReadAllView(APIView):
    required_permission = "notifications.inbox.update"

    @extend_schema(tags=["Notifications"], responses={204: OpenApiResponse()})
    def post(self, request):
        mark_all_read(user=request.user)
        return Response(status=204)
