"""MEDIA-A : upload générique presigné + multipart direct, métadonnées, download, delete."""

from django.http import HttpResponseRedirect
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.iam.exceptions import AuthAPIError
from apps.iam.services.auth_service import client_ip
from apps.media.serializers.uploads import UploadCompleteSerializer, UploadInitSerializer
from apps.media.services.upload_service import (
    complete_upload,
    delete_media,
    direct_upload,
    download_media,
    get_own_media_or_404,
    init_presigned_upload,
    serialize_media,
)


class MediaUploadInitView(APIView):
    required_permission = "media.file.upload"

    @extend_schema(
        tags=["Media"],
        request=UploadInitSerializer,
        responses={
            201: OpenApiResponse(description="upload_id + presigned_url"),
            413: OpenApiResponse(description="FILE_TOO_LARGE"),
        },
    )
    def post(self, request):
        ser = UploadInitSerializer(data=request.data or {})
        ser.is_valid(raise_exception=True)
        data = init_presigned_upload(
            user=request.user, data=ser.validated_data, actor=request.user, ip=client_ip(request)
        )
        return Response({"success": True, "data": data}, status=201)


class MediaUploadCompleteView(APIView):
    required_permission = "media.file.upload"

    @extend_schema(
        tags=["Media"],
        request=UploadCompleteSerializer,
        responses={
            200: OpenApiResponse(description="Métadonnées finales"),
            400: OpenApiResponse(description="UPLOAD_INCOMPLETE"),
            409: OpenApiResponse(description="DUPLICATE_FILE / ALREADY_COMPLETED"),
        },
    )
    def post(self, request, upload_id):
        ser = UploadCompleteSerializer(data=request.data or {})
        ser.is_valid(raise_exception=True)
        data = complete_upload(
            user=request.user,
            upload_id=upload_id,
            checksum=ser.validated_data["checksum"],
            actor=request.user,
            ip=client_ip(request),
        )
        return Response({"success": True, "data": data})


class MediaDirectUploadView(APIView):
    required_permission = "media.file.upload"
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(
        tags=["Media"],
        request={
            "multipart/form-data": {
                "type": "object",
                "properties": {
                    "file": {"type": "string", "format": "binary"},
                    "media_type": {"type": "string"},
                },
            }
        },
        responses={
            201: OpenApiResponse(description="Fichier créé"),
            413: OpenApiResponse(description="FILE_TOO_LARGE"),
            409: OpenApiResponse(description="DUPLICATE_FILE"),
        },
    )
    def post(self, request):
        uploaded = request.FILES.get("file")
        if not uploaded:
            raise AuthAPIError(400, "VALIDATION_ERROR", "Fichier requis.", extra={"field": "file"})
        data = direct_upload(
            user=request.user,
            uploaded=uploaded,
            media_type_hint=(request.data.get("media_type") or "").strip().upper(),
            actor=request.user,
            ip=client_ip(request),
        )
        return Response({"success": True, "data": data}, status=201)


class MediaDetailView(APIView):
    required_permissions = {"GET": "media.file.read", "DELETE": "media.file.delete"}

    @extend_schema(tags=["Media"], responses={200: OpenApiResponse(), 404: OpenApiResponse()})
    def get(self, request, pk):
        media = get_own_media_or_404(request.user, pk)
        return Response({"success": True, "data": serialize_media(media)})

    @extend_schema(tags=["Media"], responses={204: OpenApiResponse()})
    def delete(self, request, pk):
        media = get_own_media_or_404(request.user, pk)
        delete_media(media=media, actor=request.user, ip=client_ip(request))
        return Response(status=204)


class MediaDownloadView(APIView):
    required_permission = "media.file.read"

    @extend_schema(
        tags=["Media"],
        responses={302: OpenApiResponse(description="Redirect URL signée"), 403: OpenApiResponse()},
    )
    def get(self, request, pk):
        media = get_own_media_or_404(request.user, pk)
        url = download_media(media=media, actor=request.user, ip=client_ip(request))
        return HttpResponseRedirect(url)
