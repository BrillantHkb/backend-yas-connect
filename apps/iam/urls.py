"""Routes AUTH-A/B/C/D, montées sous /api/v1/auth/."""

from django.urls import path

from apps.iam.views import LdapLoginView, LoginView, RefreshView
from apps.iam.views_mfa import BackupRegenView, MfaVerifyView
from apps.iam.views_register import (
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
]
