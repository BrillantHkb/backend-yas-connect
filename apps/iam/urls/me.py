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

urlpatterns = [
    path("", MeView.as_view(), name="me"),  # GET /api/v1/me/ (et /me via APPEND_SLASH)
    path("password", PasswordChangeView.as_view(), name="me-password"),  # AUTH-G, avant devices
    path("tos", TosView.as_view(), name="me-tos"),
    path("tos/accept", TosAcceptView.as_view(), name="me-tos-accept"),
    path("onboarding", OnboardingView.as_view(), name="me-onboarding"),
    path("onboarding/complete", OnboardingCompleteView.as_view(), name="me-onboarding-complete"),
    path("devices", DeviceListView.as_view(), name="me-devices"),
    path("devices/current", DeviceCurrentPatchView.as_view(), name="me-devices-current"),
    path("devices/link", DeviceLinkConfirmView.as_view(), name="me-devices-link"),  # avant <uuid>
    path("devices/<uuid:pk>", DevicePatchView.as_view(), name="me-devices-patch"),
    path("devices/<uuid:pk>/revoke", DeviceRevokeView.as_view(), name="me-devices-revoke"),
    path(
        "devices/<uuid:pk>/compromise",
        DeviceCompromiseView.as_view(),
        name="me-devices-compromise",
    ),
]
