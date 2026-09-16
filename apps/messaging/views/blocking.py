"""MESSAGERIE-F : blocage utilisateur (MSG-89/90/91)."""

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.messaging.serializers.blocking import BlockUserSerializer
from apps.messaging.services import block_service


class BlockedUsersView(APIView):
    required_permissions = {"GET": "messaging.block.manage", "POST": "messaging.block.manage"}

    @extend_schema(tags=["Messagerie"], responses={200: OpenApiResponse()})
    def get(self, request):
        data = block_service.list_blocked(user=request.user)
        return Response({"success": True, "data": data})

    @extend_schema(
        tags=["Messagerie"],
        request=BlockUserSerializer,
        responses={201: OpenApiResponse(), 409: OpenApiResponse(description="ALREADY_BLOCKED")},
    )
    def post(self, request):
        ser = BlockUserSerializer(data=request.data or {})
        ser.is_valid(raise_exception=True)
        data = block_service.block_user(
            user=request.user,
            target_user_id=ser.validated_data["user_id"],
            reason=ser.validated_data["reason"],
        )
        return Response({"success": True, "data": data}, status=201)


class BlockedUserDetailView(APIView):
    required_permission = "messaging.block.manage"

    @extend_schema(tags=["Messagerie"], responses={200: OpenApiResponse()})
    def delete(self, request, user_id):
        data = block_service.unblock_user(user=request.user, target_user_id=user_id)
        return Response({"success": True, "data": data})
