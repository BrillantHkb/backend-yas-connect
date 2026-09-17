"""GET /api/v1/config — plafonds/fenêtres publics (audit W40)."""

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.config.services.public_config_service import public_config


class PublicConfigView(APIView):
    # Réutilise une perm self déjà largement accordée (iam.profile.read) —
    # aucune info sensible ici, pas besoin d'une permission dédiée.
    required_permission = "iam.profile.read"

    @extend_schema(tags=["Config"], responses={200: OpenApiResponse()})
    def get(self, request):
        return Response({"success": True, "data": public_config()})
