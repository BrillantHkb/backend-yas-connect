"""MESSAGERIE-A : inbox, création/réouverture privé, détail, archive, pin, mute, épinglés."""

from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.messaging.serializers.conversations import (
    ConversationCreateSerializer,
    ConversationMuteSerializer,
    ConversationPinSerializer,
)
from apps.messaging.services import conversation_service


def _parse_bool(raw) -> bool:
    return str(raw).strip().lower() in ("1", "true", "yes")


class ConversationListCreateView(APIView):
    required_permissions = {
        "GET": "messaging.conversation.read",
        "POST": "messaging.conversation.create",
    }

    @extend_schema(
        tags=["Messagerie"],
        parameters=[
            OpenApiParameter("archived", bool, OpenApiParameter.QUERY, required=False),
            OpenApiParameter("pinned", bool, OpenApiParameter.QUERY, required=False),
            OpenApiParameter("type", str, OpenApiParameter.QUERY, required=False),
            OpenApiParameter("limit", int, OpenApiParameter.QUERY, required=False),
            OpenApiParameter("before", str, OpenApiParameter.QUERY, required=False),
        ],
        responses={200: OpenApiResponse(description="Inbox paginée")},
    )
    def get(self, request):
        params = request.query_params
        data = conversation_service.list_inbox(
            user=request.user,
            archived=_parse_bool(params.get("archived")),
            pinned=_parse_bool(params.get("pinned")),
            type_=params.get("type"),
            limit=params.get("limit"),
            before=params.get("before"),
        )
        return Response({"success": True, "data": data})

    @extend_schema(
        tags=["Messagerie"],
        request=ConversationCreateSerializer,
        responses={
            200: OpenApiResponse(description="Fil existant (réouverture)"),
            201: OpenApiResponse(description="Fil créé"),
            403: OpenApiResponse(description="USER_BLOCKED"),
            404: OpenApiResponse(description="NOT_FOUND"),
        },
    )
    def post(self, request):
        ser = ConversationCreateSerializer(data=request.data or {})
        ser.is_valid(raise_exception=True)
        data, created = conversation_service.find_or_create_private(
            user=request.user, participant_id=ser.validated_data["participant_id"]
        )
        return Response({"success": True, "data": data}, status=201 if created else 200)


class ConversationDetailView(APIView):
    required_permission = "messaging.conversation.read"

    @extend_schema(
        tags=["Messagerie"],
        responses={200: OpenApiResponse(), 404: OpenApiResponse(description="NOT_FOUND")},
    )
    def get(self, request, pk):
        data = conversation_service.get_detail(user=request.user, conversation_id=pk)
        return Response({"success": True, "data": data})


class ConversationByUuidView(APIView):
    required_permission = "messaging.conversation.read"

    @extend_schema(
        tags=["Messagerie"],
        responses={200: OpenApiResponse(), 404: OpenApiResponse(description="NOT_FOUND")},
    )
    def get(self, request, conversation_uuid):
        data = conversation_service.get_detail(
            user=request.user, conversation_uuid=conversation_uuid
        )
        return Response({"success": True, "data": data})


class ConversationArchiveView(APIView):
    required_permission = "messaging.conversation.archive"

    @extend_schema(tags=["Messagerie"], responses={200: OpenApiResponse()})
    def post(self, request, pk):
        data = conversation_service.set_archived(
            user=request.user, conversation_id=pk, archived=True
        )
        return Response({"success": True, "data": data})

    @extend_schema(tags=["Messagerie"], responses={200: OpenApiResponse()})
    def delete(self, request, pk):
        data = conversation_service.set_archived(
            user=request.user, conversation_id=pk, archived=False
        )
        return Response({"success": True, "data": data})


class ConversationPinView(APIView):
    required_permission = "messaging.conversation.read"

    @extend_schema(
        tags=["Messagerie"], request=ConversationPinSerializer, responses={200: OpenApiResponse()}
    )
    def patch(self, request, pk):
        ser = ConversationPinSerializer(data=request.data or {})
        ser.is_valid(raise_exception=True)
        data = conversation_service.set_pinned(
            user=request.user, conversation_id=pk, pinned=ser.validated_data["pinned"]
        )
        return Response({"success": True, "data": data})


class ConversationMuteView(APIView):
    required_permission = "messaging.conversation.read"

    @extend_schema(
        tags=["Messagerie"], request=ConversationMuteSerializer, responses={200: OpenApiResponse()}
    )
    def patch(self, request, pk):
        ser = ConversationMuteSerializer(data=request.data or {})
        ser.is_valid(raise_exception=True)
        data = conversation_service.set_muted(
            user=request.user, conversation_id=pk, muted=ser.validated_data["muted"]
        )
        return Response({"success": True, "data": data})


class ConversationPinnedMessagesView(APIView):
    required_permission = "messaging.conversation.read"

    @extend_schema(tags=["Messagerie"], responses={200: OpenApiResponse()})
    def get(self, request, pk):
        data = conversation_service.list_pinned_messages(user=request.user, conversation_id=pk)
        return Response({"success": True, "data": data})
