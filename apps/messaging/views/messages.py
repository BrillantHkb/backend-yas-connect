"""MESSAGERIE-B : historique, envoi, détail, édition, suppression, recherche."""

from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.iam.services.device_service import current_device
from apps.messaging.serializers.messages import MessageEditSerializer, MessageSendSerializer
from apps.messaging.services import message_service


class MessageListCreateView(APIView):
    required_permissions = {
        "GET": "messaging.message.read",
        "POST": "messaging.message.send",
    }

    @extend_schema(
        tags=["Messagerie"],
        parameters=[
            OpenApiParameter("before", str, OpenApiParameter.QUERY, required=False),
            OpenApiParameter("limit", int, OpenApiParameter.QUERY, required=False),
            OpenApiParameter("parent_id", str, OpenApiParameter.QUERY, required=False),
        ],
        responses={200: OpenApiResponse(description="Historique paginé")},
    )
    def get(self, request, pk):
        params = request.query_params
        data = message_service.list_messages(
            user=request.user,
            conversation_id=pk,
            before=params.get("before"),
            limit=params.get("limit"),
            parent_id=params.get("parent_id"),
        )
        return Response({"success": True, "data": data})

    @extend_schema(
        tags=["Messagerie"],
        request=MessageSendSerializer,
        responses={
            201: OpenApiResponse(description="Message envoyé"),
            409: OpenApiResponse(
                description="DUPLICATE_MESSAGE / CRYPTO_KEYS_MISSING / PEER_KEYS_MISSING"
            ),
            422: OpenApiResponse(description="MEDIA_INFECTED"),
        },
    )
    def post(self, request, pk):
        ser = MessageSendSerializer(data=request.data or {})
        ser.is_valid(raise_exception=True)
        device = current_device(request)
        data = message_service.send_message(
            user=request.user, device=device, conversation_id=pk, data=ser.validated_data
        )
        return Response({"success": True, "data": data}, status=201)


class MessageDetailView(APIView):
    required_permissions = {
        "GET": "messaging.message.read",
        "PATCH": "messaging.message.update",
        "DELETE": "messaging.message.delete",
    }

    @extend_schema(
        tags=["Messagerie"],
        responses={200: OpenApiResponse(), 404: OpenApiResponse(description="NOT_FOUND")},
    )
    def get(self, request, pk):
        data = message_service.get_message_detail(user=request.user, pk=pk)
        return Response({"success": True, "data": data})

    @extend_schema(
        tags=["Messagerie"],
        request=MessageEditSerializer,
        responses={
            200: OpenApiResponse(),
            403: OpenApiResponse(description="FORBIDDEN / EDIT_WINDOW_EXPIRED"),
        },
    )
    def patch(self, request, pk):
        ser = MessageEditSerializer(data=request.data or {})
        ser.is_valid(raise_exception=True)
        data = message_service.edit_message(
            user=request.user, pk=pk, encrypted_content_b64=ser.validated_data["encrypted_content"]
        )
        return Response({"success": True, "data": data})

    @extend_schema(
        tags=["Messagerie"],
        parameters=[OpenApiParameter("scope", str, OpenApiParameter.QUERY, required=False)],
        responses={
            200: OpenApiResponse(),
            403: OpenApiResponse(description="FORBIDDEN / DELETE_WINDOW_EXPIRED"),
        },
    )
    def delete(self, request, pk):
        scope = request.query_params.get("scope", "SELF")
        data = message_service.delete_message(user=request.user, pk=pk, scope=scope)
        return Response({"success": True, "data": data})


class MessageSearchView(APIView):
    required_permission = "messaging.message.read"

    @extend_schema(
        tags=["Messagerie"],
        parameters=[OpenApiParameter("q", str, OpenApiParameter.QUERY, required=True)],
        responses={200: OpenApiResponse(), 400: OpenApiResponse(description="VALIDATION_ERROR")},
    )
    def get(self, request, pk):
        data = message_service.search_messages(
            user=request.user, conversation_id=pk, q=request.query_params.get("q")
        )
        return Response({"success": True, "data": data})
