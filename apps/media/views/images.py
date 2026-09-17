"""MEDIA-B : PATCH image, POST optimize."""

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.media.serializers.images import ImageUpdateSerializer
from apps.media.services import image_service


class MediaImageView(APIView):
    required_permission = "media.image.manage"

    @extend_schema(
        tags=["Media"],
        request=ImageUpdateSerializer,
        responses={200: OpenApiResponse(), 404: OpenApiResponse()},
    )
    def patch(self, request, pk):
        ser = ImageUpdateSerializer(data=request.data or {})
        ser.is_valid(raise_exception=True)
        image = image_service.update_image(user=request.user, pk=pk, data=ser.validated_data)
        return Response({"success": True, "data": image_service.serialize_image(image)})


class MediaImageOptimizeView(APIView):
    required_permission = "media.image.manage"

    @extend_schema(tags=["Media"], responses={202: OpenApiResponse()})
    def post(self, request, pk):
        image_service.optimize_image(user=request.user, pk=pk)
        return Response({"success": True, "data": {"optimized": True}}, status=202)
