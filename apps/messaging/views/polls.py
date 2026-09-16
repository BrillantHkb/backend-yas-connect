"""MESSAGERIE-E : vote et clôture de sondage (MSG-82/83)."""

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.messaging.serializers.polls import PollVoteSerializer
from apps.messaging.services import poll_service


class PollVoteView(APIView):
    required_permission = "messaging.poll.vote"

    @extend_schema(
        tags=["Messagerie"],
        request=PollVoteSerializer,
        responses={200: OpenApiResponse(), 403: OpenApiResponse(description="POLL_CLOSED")},
    )
    def post(self, request, pk):
        ser = PollVoteSerializer(data=request.data or {})
        ser.is_valid(raise_exception=True)
        data = poll_service.vote(
            user=request.user, poll_id=pk, option_ids=ser.validated_data["option_ids"]
        )
        return Response({"success": True, "data": data})


class PollCloseView(APIView):
    required_permission = "messaging.poll.vote"

    @extend_schema(tags=["Messagerie"], responses={200: OpenApiResponse(), 403: OpenApiResponse()})
    def post(self, request, pk):
        data = poll_service.close_poll(user=request.user, poll_id=pk)
        return Response({"success": True, "data": data})
