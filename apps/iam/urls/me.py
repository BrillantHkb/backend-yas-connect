"""AUTH-E / AUTH-F sous /api/v1/me/ — JWT, owner. Pas HasPermission ce jour."""

from django.urls import path

from apps.iam.views.compliance import (
    OnboardingCompleteView,
    OnboardingView,
    TosAcceptView,
    TosView,
)
from apps.iam.views.device_link import DeviceLinkConfirmView
from apps.iam.views.devices import (
    DeviceCompromiseView,
    DeviceCurrentPatchView,
    DeviceListView,
    DevicePatchView,
    DeviceRevokeView,
)
from apps.iam.views.me import MeView
from apps.iam.views.password import PasswordChangeView
from apps.iam.views.prefs import MePreferencesView
from apps.media.views.avatar import MeAvatarView
from apps.iam.views.security import EmailChangeView, EmailResendView, LoginHistoryView
from apps.iam.views.sessions import (
    DeviceSessionsLogoutView,
    HeartbeatView,
    SessionListView,
    SessionLogoutView,
)

urlpatterns = [
    path("", MeView.as_view(), name="me"),  # GET+PATCH /api/v1/me/
    path("avatar", MeAvatarView.as_view(), name="me-avatar"),  # PROF-A, avant tout catch-all
    path("preferences", MePreferencesView.as_view(), name="me-preferences"),  # PROF-B
    path("password", PasswordChangeView.as_view(), name="me-password"),  # AUTH-G, avant devices
    path("email", EmailChangeView.as_view(), name="me-email"),  # AUTH-I, avant email/resend
    path("email/resend", EmailResendView.as_view(), name="me-email-resend"),
    path("security/logins", LoginHistoryView.as_view(), name="me-security-logins"),
    path("tos", TosView.as_view(), name="me-tos"),
    path("tos/accept", TosAcceptView.as_view(), name="me-tos-accept"),
    path("onboarding", OnboardingView.as_view(), name="me-onboarding"),
    path("onboarding/complete", OnboardingCompleteView.as_view(), name="me-onboarding-complete"),
    path("sessions", SessionListView.as_view(), name="me-sessions"),
    path(
        "sessions/current/heartbeat",
        HeartbeatView.as_view(),
        name="me-sessions-heartbeat",  # avant sessions/<uuid>
    ),
    path("sessions/<uuid:pk>/logout", SessionLogoutView.as_view(), name="me-session-logout"),
    path("devices", DeviceListView.as_view(), name="me-devices"),
    path("devices/current", DeviceCurrentPatchView.as_view(), name="me-devices-current"),
    path("devices/link", DeviceLinkConfirmView.as_view(), name="me-devices-link"),  # avant <uuid>
    path("devices/<uuid:pk>", DevicePatchView.as_view(), name="me-devices-patch"),
    path("devices/<uuid:pk>/revoke", DeviceRevokeView.as_view(), name="me-devices-revoke"),
    path(
        "devices/<uuid:pk>/logout",
        DeviceSessionsLogoutView.as_view(),
        name="me-devices-logout",
    ),
    path(
        "devices/<uuid:pk>/compromise",
        DeviceCompromiseView.as_view(),
        name="me-devices-compromise",
    ),
]
