"""AUTH-H : logout, liste de sessions, heartbeat. JWT + iam.session.*."""

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.iam.exceptions import AuthAPIError
from apps.iam.serializers.sessions import (
    HeartbeatEnvelopeSerializer,
    SessionListEnvelopeSerializer,
    SessionOkEnvelopeSerializer,
)
from apps.iam.services.session_service import (
    heartbeat_current,
    list_sessions,
    logout_all,
    logout_current,
    logout_device_sessions,
    logout_session,
)


def _yas_session(request):
    session = getattr(request, "yas_session", None)
    if session is None:
        raise AuthAPIError(401, "UNAUTHENTICATED", "Session invalide.")
    return session


class LogoutView(APIView):
    """POST /api/v1/auth/logout — session courante seulement."""

    required_permission = "iam.session.logout"

    @extend_schema(
        tags=["Auth"],
        request=None,
        responses={200: SessionOkEnvelopeSerializer},
        description="Coupe la session du Bearer (LOGOUT). Les autres appareils restent connectés.",
    )
    def post(self, request):
        logout_current(session=_yas_session(request))
        return Response({"success": True})


class LogoutAllView(APIView):
    """POST /api/v1/auth/logout-all — partout, y compris courant."""

    required_permission = "iam.session.logout"

    @extend_schema(
        tags=["Auth"],
        request=None,
        responses={200: SessionOkEnvelopeSerializer},
        description="Coupe toutes les sessions (LOGOUT_ALL). Relogin + TOTP partout.",
    )
    def post(self, request):
        logout_all(user=request.user)
        return Response({"success": True})


class SessionListView(APIView):
    """GET /api/v1/me/sessions — actives, is_current, jamais hash/JTI."""

    required_permission = "iam.session.read"

    @extend_schema(
        tags=["Me"],
        responses={200: SessionListEnvelopeSerializer},
        description="Sessions vivantes (pas idle / pas plafond). Hash et JTI jamais renvoyés.",
    )
    def get(self, request):
        current = _yas_session(request)
        sessions = list_sessions(user=request.user, current_session_id=current.id)
        return Response({"success": True, "data": {"sessions": sessions}})


class SessionLogoutView(APIView):
    """POST /api/v1/me/sessions/{id}/logout — owner. 404 si autre user."""

    required_permission = "iam.session.logout"

    @extend_schema(
        tags=["Me"],
        request=None,
        responses={
            200: SessionOkEnvelopeSerializer,
            404: OpenApiResponse(description="NOT_FOUND"),
        },
        description="Coupe une session. {id} = courante → même effet que POST /auth/logout.",
    )
    def post(self, request, pk):
        logout_session(user=request.user, session_id=pk)
        return Response({"success": True})


class DeviceSessionsLogoutView(APIView):
    """POST /api/v1/me/devices/{id}/logout — sessions de l’appareil, push/trusted intacts."""

    required_permission = "iam.session.logout"

    @extend_schema(
        tags=["Me"],
        request=None,
        responses={
            200: SessionOkEnvelopeSerializer,
            404: OpenApiResponse(description="NOT_FOUND"),
        },
        description=(
            "Coupe les sessions de cet appareil. Ne vide pas push_token / trusted "
            "(ça c’est POST .../revoke)."
        ),
    )
    def post(self, request, pk):
        logout_device_sessions(user=request.user, device_id=pk)
        return Response({"success": True})


class HeartbeatView(APIView):
    """POST /api/v1/me/sessions/current/heartbeat — last_activity, debounce 60 s."""

    required_permission = "iam.session.heartbeat"

    @extend_schema(
        tags=["Me"],
        request=None,
        responses={200: HeartbeatEnvelopeSerializer},
        description="Remet l’idle à zéro si ≥ 60 s. N’écrit pas users.status. N’allonge pas 30 j.",
    )
    def post(self, request):
        data = heartbeat_current(session=_yas_session(request))
        return Response({"success": True, "data": data})
