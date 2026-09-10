"""Routes AUTH-A/B/C/D, montées sous /api/v1/auth/."""

from django.urls import path

from apps.iam.views.auth import LdapLoginView, LoginView, RefreshView
from apps.iam.views.device_link import DeviceLinkStartView, DeviceLinkStatusView
from apps.iam.views.mfa import BackupRegenView, MfaVerifyView
from apps.iam.views.password import (
    PasswordForgotView,
    PasswordResetVerifyView,
    PasswordResetView,
)
from apps.iam.views.register import (
    CheckAdView,
    RegisterAdView,
    RegisterLocalView,
    ResendVerificationView,
    VerifyEmailView,
)

urlpatterns = [
    path("login", LoginView.as_view(), name="login"),
    path("login/ldap", LdapLoginView.as_view(), name="login-ldap"),  # AUTH-B, pas de JIT
    path("refresh", RefreshView.as_view(), name="refresh"),
    path("mfa/verify", MfaVerifyView.as_view(), name="mfa-verify"),  # AUTH-C, public
    path(
        "mfa/backup-codes/regenerate",
        BackupRegenView.as_view(),
        name="mfa-backup-regen",  # JWT déjà MFA ; pas HasPermission ce jour
    ),
    path("register/check-ad", CheckAdView.as_view(), name="register-check-ad"),
    path("register/ad", RegisterAdView.as_view(), name="register-ad"),
    path("register", RegisterLocalView.as_view(), name="register"),
    path("register/verify-email", VerifyEmailView.as_view(), name="register-verify-email"),
    path("register/resend-verification", ResendVerificationView.as_view(), name="register-resend"),
    path("device-link/start", DeviceLinkStartView.as_view(), name="device-link-start"),
    path(
        "device-link/<uuid:challenge_id>",
        DeviceLinkStatusView.as_view(),
        name="device-link-status",
    ),
    path("password/forgot", PasswordForgotView.as_view(), name="password-forgot"),
    path(
        "password/reset/verify",
        PasswordResetVerifyView.as_view(),
        name="password-reset-verify",  # avant password/reset
    ),
    path("password/reset", PasswordResetView.as_view(), name="password-reset"),
]
