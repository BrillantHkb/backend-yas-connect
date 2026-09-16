"""MESSAGERIE-E : réactions emoji (MSG-73/74)."""

from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.messaging.serializers.reactions import ReactionSerializer
from apps.messaging.services import reaction_service


class MessageReactionsView(APIView):
    required_permission = "messaging.message.react"

    @extend_schema(
        tags=["Messagerie"], request=ReactionSerializer, responses={201: OpenApiResponse()}
    )
    def post(self, request, pk):
        ser = ReactionSerializer(data=request.data or {})
        ser.is_valid(raise_exception=True)
        data = reaction_service.add_reaction(
            user=request.user, pk=pk, emoji=ser.validated_data["emoji"]
        )
        return Response({"success": True, "data": data}, status=201)

    @extend_schema(
        tags=["Messagerie"],
        parameters=[OpenApiParameter("emoji", str, OpenApiParameter.QUERY, required=True)],
        responses={200: OpenApiResponse()},
    )
    def delete(self, request, pk):
        data = reaction_service.remove_reaction(
            user=request.user, pk=pk, emoji=request.query_params.get("emoji")
        )
        return Response({"success": True, "data": data})
