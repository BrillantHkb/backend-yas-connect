"""AUTH-E sous /api/v1/me/ — JWT, owner. Pas HasPermission ce jour."""

from django.urls import path

from apps.iam.views.device_link import DeviceLinkConfirmView
from apps.iam.views.devices import (
    DeviceCompromiseView,
    DeviceCurrentPatchView,
    DeviceListView,
    DevicePatchView,
    DeviceRevokeView,
)

urlpatterns = [
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
