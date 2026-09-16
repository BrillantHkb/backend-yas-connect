"""MESSAGERIE-A : inbox, création/réouverture privé, détail, archive, pin, mute, épinglés."""

from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.messaging.serializers.conversations import (
    ConversationCreateSerializer,
    ConversationMuteSerializer,
    ConversationPinSerializer,
    ConversationUpdateSerializer,
    GroupSettingsSerializer,
    MemberAddSerializer,
    MemberUpdateSerializer,
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
        vd = ser.validated_data
        if vd["type"] == "PRIVATE":
            data, created = conversation_service.find_or_create_private(
                user=request.user, participant_id=vd["participant_id"]
            )
        else:
            data, created = conversation_service.create_group(
                user=request.user,
                title=vd["title"],
                member_ids=vd["member_ids"],
                visibility=vd["visibility"],
            )
        return Response({"success": True, "data": data}, status=201 if created else 200)


class ConversationDetailView(APIView):
    """GET détail (MESSAGERIE-A) + PATCH métadonnées groupe (MSG-42/43, GROUP seulement)."""

    required_permissions = {
        "GET": "messaging.conversation.read",
        "PATCH": "messaging.conversation.update",
    }

    @extend_schema(
        tags=["Messagerie"],
        responses={200: OpenApiResponse(), 404: OpenApiResponse(description="NOT_FOUND")},
    )
    def get(self, request, pk):
        data = conversation_service.get_detail(user=request.user, conversation_id=pk)
        return Response({"success": True, "data": data})

    @extend_schema(
        tags=["Messagerie"],
        request=ConversationUpdateSerializer,
        responses={200: OpenApiResponse()},
    )
    def patch(self, request, pk):
        ser = ConversationUpdateSerializer(data=request.data or {})
        ser.is_valid(raise_exception=True)
        data = conversation_service.update_conversation(
            user=request.user, conversation_id=pk, data=ser.validated_data
        )
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


class GroupSettingsView(APIView):
    """PATCH /conversations/{id}/group-settings — visibilité, locked, max_members, accueil."""

    required_permission = "messaging.conversation.update"

    @extend_schema(
        tags=["Messagerie"], request=GroupSettingsSerializer, responses={200: OpenApiResponse()}
    )
    def patch(self, request, pk):
        ser = GroupSettingsSerializer(data=request.data or {})
        ser.is_valid(raise_exception=True)
        data = conversation_service.update_group_settings(
            user=request.user, conversation_id=pk, data=ser.validated_data
        )
        return Response({"success": True, "data": data})


class MemberListCreateView(APIView):
    """MSG-44 : GET liste / POST ajouter un membre."""

    required_permissions = {"GET": "messaging.member.read", "POST": "messaging.member.manage"}

    @extend_schema(
        tags=["Messagerie"],
        parameters=[OpenApiParameter("active", bool, OpenApiParameter.QUERY, required=False)],
        responses={200: OpenApiResponse()},
    )
    def get(self, request, pk):
        raw = request.query_params.get("active")
        active = True if raw is None else _parse_bool(raw)
        data = conversation_service.list_members(
            user=request.user, conversation_id=pk, active=active
        )
        return Response({"success": True, "data": data})

    @extend_schema(
        tags=["Messagerie"],
        request=MemberAddSerializer,
        responses={
            201: OpenApiResponse(),
            403: OpenApiResponse(description="FORBIDDEN / INVITE_REFUSED / USER_BLOCKED"),
            409: OpenApiResponse(description="ALREADY_MEMBER / GROUP_FULL"),
        },
    )
    def post(self, request, pk):
        ser = MemberAddSerializer(data=request.data or {})
        ser.is_valid(raise_exception=True)
        data = conversation_service.add_member(
            user=request.user,
            conversation_id=pk,
            target_user_id=ser.validated_data["user_id"],
            role=ser.validated_data["role"],
        )
        return Response({"success": True, "data": data}, status=201)


class MemberDetailView(APIView):
    """MSG-47/48/56 (PATCH rôle/pseudo) + MSG-45 (DELETE retirer)."""

    required_permission = "messaging.member.manage"

    @extend_schema(
        tags=["Messagerie"], request=MemberUpdateSerializer, responses={200: OpenApiResponse()}
    )
    def patch(self, request, pk, user_id):
        ser = MemberUpdateSerializer(data=request.data or {})
        ser.is_valid(raise_exception=True)
        data = conversation_service.update_member(
            user=request.user, conversation_id=pk, target_user_id=user_id, data=ser.validated_data
        )
        return Response({"success": True, "data": data})

    @extend_schema(
        tags=["Messagerie"],
        responses={200: OpenApiResponse(), 403: OpenApiResponse(description="OWNER_MUST_TRANSFER")},
    )
    def delete(self, request, pk, user_id):
        data = conversation_service.remove_member(
            user=request.user, conversation_id=pk, target_user_id=user_id
        )
        return Response({"success": True, "data": data})


class ConversationLeaveView(APIView):
    """POST /conversations/{id}/leave — MSG-46."""

    required_permission = "messaging.conversation.read"

    @extend_schema(
        tags=["Messagerie"],
        responses={200: OpenApiResponse(), 403: OpenApiResponse(description="OWNER_MUST_TRANSFER")},
    )
    def post(self, request, pk):
        data = conversation_service.leave_conversation(user=request.user, conversation_id=pk)
        return Response({"success": True, "data": data})
