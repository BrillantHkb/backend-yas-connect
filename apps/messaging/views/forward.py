"""MESSAGERIE-E : transfert de message (MSG-75/76)."""

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.messaging.serializers.forward import ForwardSerializer
from apps.messaging.services import forward_service


class MessageForwardView(APIView):
    required_permission = "messaging.message.forward"

    @extend_schema(
        tags=["Messagerie"],
        request=ForwardSerializer,
        responses={
            201: OpenApiResponse(),
            400: OpenApiResponse(description="VALIDATION_ERROR (encrypted_content requis)"),
        },
    )
    def post(self, request, pk):
        ser = ForwardSerializer(data=request.data or {})
        ser.is_valid(raise_exception=True)
        data = forward_service.forward_message(
            user=request.user,
            message_id=pk,
            target_conversation_id=ser.validated_data["conversation_id"],
            encrypted_content_b64=ser.validated_data["encrypted_content"],
        )
        return Response({"success": True, "data": data}, status=201)
