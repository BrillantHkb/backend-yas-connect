"""MEDIA-E : GED."""

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.media.serializers.documents import (
    DocumentCreateSerializer,
    DocumentUpdateSerializer,
    DocumentVersionCreateSerializer,
)
from apps.media.services import document_service


class DocumentListCreateView(APIView):
    required_permission = "media.document.manage"

    @extend_schema(
        tags=["Media"],
        request=DocumentCreateSerializer,
        responses={201: OpenApiResponse(), 409: OpenApiResponse(description="ALREADY_DOCUMENT")},
    )
    def post(self, request):
        ser = DocumentCreateSerializer(data=request.data or {})
        ser.is_valid(raise_exception=True)
        vd = ser.validated_data
        data = document_service.create_document(
            user=request.user,
            upload_id=vd["upload_id"],
            title=vd["title"],
            category=vd["category"],
            confidential=vd["confidential"],
        )
        return Response({"success": True, "data": data}, status=201)


class DocumentDetailView(APIView):
    required_permissions = {"GET": "media.document.read", "PATCH": "media.document.manage"}

    @extend_schema(tags=["Media"], responses={200: OpenApiResponse(), 404: OpenApiResponse()})
    def get(self, request, pk):
        data = document_service.get_document(user=request.user, pk=pk)
        return Response({"success": True, "data": data})

    @extend_schema(
        tags=["Media"], request=DocumentUpdateSerializer, responses={200: OpenApiResponse()}
    )
    def patch(self, request, pk):
        ser = DocumentUpdateSerializer(data=request.data or {})
        ser.is_valid(raise_exception=True)
        data = document_service.update_document(user=request.user, pk=pk, data=ser.validated_data)
        return Response({"success": True, "data": data})


class DocumentVersionsView(APIView):
    required_permissions = {"GET": "media.document.read", "POST": "media.document.manage"}

    @extend_schema(tags=["Media"], responses={200: OpenApiResponse()})
    def get(self, request, pk):
        data = document_service.list_versions(user=request.user, pk=pk)
        return Response({"success": True, "data": data})

    @extend_schema(
        tags=["Media"], request=DocumentVersionCreateSerializer, responses={201: OpenApiResponse()}
    )
    def post(self, request, pk):
        ser = DocumentVersionCreateSerializer(data=request.data or {})
        ser.is_valid(raise_exception=True)
        vd = ser.validated_data
        data = document_service.add_version(
            user=request.user, pk=pk, upload_id=vd["upload_id"], comment=vd["comment"]
        )
        return Response({"success": True, "data": data}, status=201)


class DocumentPreviewView(APIView):
    required_permission = "media.document.read"

    @extend_schema(tags=["Media"], responses={200: OpenApiResponse(), 403: OpenApiResponse()})
    def get(self, request, pk):
        url = document_service.preview_url(user=request.user, pk=pk)
        return Response({"success": True, "data": {"preview_url": url}})
