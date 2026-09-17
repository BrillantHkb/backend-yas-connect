"""CRYPTO-A : 5 vues clés (identity, signed-prekey, one-time-prekeys, count, bundles)."""

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.crypto.serializers.keys import (
    IdentitySerializer,
    OneTimePrekeysBatchSerializer,
    SignedPrekeySerializer,
)
from apps.crypto.services.key_service import (
    get_bundles,
    get_target_user_or_404,
    load_otpks,
    otpk_count,
    upsert_identity,
    upsert_signed_prekey,
)
from apps.iam.services.device_service import current_device


class IdentityView(APIView):
    """PUT /api/v1/crypto/me/identity — CRY-01, upsert 1-1 appareil."""

    required_permission = "crypto.keys.manage"

    @extend_schema(
        tags=["Crypto"],
        request=IdentitySerializer,
        responses={200: OpenApiResponse(), 400: OpenApiResponse(description="VALIDATION_ERROR")},
    )
    def put(self, request):
        ser = IdentitySerializer(data=request.data or {})
        ser.is_valid(raise_exception=True)
        device = current_device(request)
        data = upsert_identity(
            device=device,
            registration_id=ser.validated_data["registration_id"],
            identity_public_key_b64=ser.validated_data["identity_public_key"],
        )
        return Response({"success": True, "data": data})


class SignedPrekeyView(APIView):
    """PUT /api/v1/crypto/me/signed-prekey — CRY-02, rotation = nouveau key_id."""

    required_permission = "crypto.keys.manage"

    @extend_schema(
        tags=["Crypto"],
        request=SignedPrekeySerializer,
        responses={200: OpenApiResponse(), 400: OpenApiResponse(description="VALIDATION_ERROR")},
    )
    def put(self, request):
        ser = SignedPrekeySerializer(data=request.data or {})
        ser.is_valid(raise_exception=True)
        device = current_device(request)
        data = upsert_signed_prekey(
            device=device,
            key_id=ser.validated_data["key_id"],
            public_key_b64=ser.validated_data["public_key"],
            signature_b64=ser.validated_data["signature"],
        )
        return Response({"success": True, "data": data})


class OneTimePrekeysView(APIView):
    """PUT /api/v1/crypto/me/one-time-prekeys — CRY-03, batch max 100."""

    required_permission = "crypto.keys.manage"

    @extend_schema(
        tags=["Crypto"],
        request=OneTimePrekeysBatchSerializer,
        responses={200: OpenApiResponse(), 400: OpenApiResponse(description="VALIDATION_ERROR")},
    )
    def put(self, request):
        ser = OneTimePrekeysBatchSerializer(data=request.data or {})
        ser.is_valid(raise_exception=True)
        device = current_device(request)
        data = load_otpks(device=device, keys=ser.validated_data["keys"])
        return Response({"success": True, "data": data})


class OneTimePrekeyCountView(APIView):
    """GET /api/v1/crypto/me/one-time-prekeys/count — CRY-04."""

    required_permission = "crypto.keys.manage"

    @extend_schema(tags=["Crypto"], responses={200: OpenApiResponse()})
    def get(self, request):
        device = current_device(request)
        return Response({"success": True, "data": {"available": otpk_count(device=device)}})


class BundlesView(APIView):
    """GET /api/v1/crypto/users/{id}/bundles — CRY-05/06/14, consomme 1 OTPK/appareil.

    ?device_id= (audit W37) cible un seul appareil du contact au lieu de tous,
    pour ne pas gaspiller un OTPK par appareil quand un seul est nécessaire.
    """

    required_permission = "crypto.bundle.read"

    @extend_schema(
        tags=["Crypto"],
        responses={
            200: OpenApiResponse(description="Bundles Signal, un par appareil"),
            400: OpenApiResponse(description="VALIDATION_ERROR"),
            404: OpenApiResponse(description="NOT_FOUND"),
            409: OpenApiResponse(description="PEER_KEYS_MISSING"),
        },
    )
    def get(self, request, pk):
        target = get_target_user_or_404(pk)
        data = get_bundles(target_user=target, device_id=request.query_params.get("device_id"))
        return Response({"success": True, "data": data})
