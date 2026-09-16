"""MESSAGERIE-E : signets (MSG-79/80)."""

from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.messaging.serializers.bookmarks import BookmarkSerializer
from apps.messaging.services import bookmark_service


class MessageBookmarksView(APIView):
    required_permission = "messaging.bookmark.manage"

    @extend_schema(
        tags=["Messagerie"], request=BookmarkSerializer, responses={201: OpenApiResponse()}
    )
    def post(self, request, pk):
        ser = BookmarkSerializer(data=request.data or {})
        ser.is_valid(raise_exception=True)
        data = bookmark_service.add_bookmark(
            user=request.user, pk=pk, note=ser.validated_data["note"]
        )
        return Response({"success": True, "data": data}, status=201)

    @extend_schema(tags=["Messagerie"], responses={200: OpenApiResponse()})
    def delete(self, request, pk):
        data = bookmark_service.remove_bookmark(user=request.user, pk=pk)
        return Response({"success": True, "data": data})


class MyBookmarksView(APIView):
    required_permission = "messaging.bookmark.manage"

    @extend_schema(
        tags=["Messagerie"],
        parameters=[
            OpenApiParameter("before", str, OpenApiParameter.QUERY, required=False),
            OpenApiParameter("limit", int, OpenApiParameter.QUERY, required=False),
        ],
        responses={200: OpenApiResponse()},
    )
    def get(self, request):
        params = request.query_params
        data = bookmark_service.list_bookmarks(
            user=request.user, before=params.get("before"), limit=params.get("limit")
        )
        return Response({"success": True, "data": data})
