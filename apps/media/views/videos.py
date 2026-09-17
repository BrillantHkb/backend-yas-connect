"""MEDIA-C : transcodage, stream, miniature."""

from django.http import HttpResponseRedirect
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.media.services import video_service


class MediaVideoTranscodeView(APIView):
    required_permission = "media.video.manage"

    @extend_schema(tags=["Media"], responses={202: OpenApiResponse()})
    def post(self, request, pk):
        video = video_service.transcode(user=request.user, pk=pk)
        return Response(
            {"success": True, "data": {"transcoding_status": video.transcoding_status}},
            status=202,
        )


class MediaVideoStreamView(APIView):
    required_permission = "media.file.read"

    @extend_schema(
        tags=["Media"],
        responses={200: OpenApiResponse(), 409: OpenApiResponse(description="VIDEO_NOT_READY")},
    )
    def get(self, request, pk):
        url = video_service.stream_url(user=request.user, pk=pk)
        return Response({"success": True, "data": {"stream_url": url}})


class MediaVideoThumbnailView(APIView):
    required_permission = "media.file.read"

    @extend_schema(tags=["Media"], responses={302: OpenApiResponse(), 404: OpenApiResponse()})
    def get(self, request, pk):
        url = video_service.thumbnail_url(user=request.user, pk=pk)
        return HttpResponseRedirect(url)
