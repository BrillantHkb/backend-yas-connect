"""CRYPTO-A : /api/v1/crypto/."""

from django.urls import path

from apps.crypto.views.keys import (
    BundlesView,
    IdentityView,
    OneTimePrekeyCountView,
    OneTimePrekeysView,
    SignedPrekeyView,
)

urlpatterns = [
    path("me/identity", IdentityView.as_view(), name="crypto-me-identity"),
    path("me/signed-prekey", SignedPrekeyView.as_view(), name="crypto-me-signed-prekey"),
    path(
        "me/one-time-prekeys/count",
        OneTimePrekeyCountView.as_view(),
        name="crypto-me-otpk-count",  # avant me/one-time-prekeys
    ),
    path("me/one-time-prekeys", OneTimePrekeysView.as_view(), name="crypto-me-otpk"),
    path("users/<uuid:pk>/bundles", BundlesView.as_view(), name="crypto-user-bundles"),
]
