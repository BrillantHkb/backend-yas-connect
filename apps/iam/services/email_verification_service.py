"""AUTH-I / D04 : tickets e-mail REGISTER et EMAIL_CHANGE (hash SHA-256)."""

from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from apps.iam.exceptions import AuthAPIError
from apps.iam.models import EmailVerification, User
from apps.iam.services import rate_limit_service
from apps.iam.services.notify_stub import notify_email_verification

logger = logging.getLogger(__name__)

MSG_INVALID_TOKEN = "Token invalide ou expiré."
MSG_FORBIDDEN = "L’adresse est gérée par Active Directory."
MSG_UNCHANGED = "Adresse identique à l’actuelle."
MSG_CONFLICT = "Cette adresse e-mail est déjà utilisée."
MSG_NO_PENDING = "Aucun changement d’e-mail en attente."
MSG_RESEND_LIMIT = "Trop de renvois. Réessayez plus tard."


def hash_email_token(raw: str) -> str:
    """SHA-256 AUTH-D — pas HMAC refresh (tokens lab déjà émis)."""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def issue_email_verification(
    user: User,
    *,
    email: str,
    purpose: str,
) -> tuple[str, bool]:
    """Révoque les tickets unused du même purpose, crée un nouveau, stub mail."""
    now = timezone.now()
    EmailVerification.objects.filter(
        user=user,
        purpose=purpose,
        verified_at__isnull=True,
        revoked_at__isnull=True,
    ).update(revoked_at=now)
    raw = secrets.token_urlsafe(32)
    EmailVerification.objects.create(
        user=user,
        email=email,
        token_hash=hash_email_token(raw),
        purpose=purpose,
        expires_at=now + timedelta(hours=settings.EMAIL_VERIFICATION_TTL_HOURS),
    )
    sent = False
    if settings.EMAIL_HOST:
        try:
            send_mail(
                subject="YAS Connect — confirmez votre e-mail",
                message=f"Token de vérification : {raw}",
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[email],
                fail_silently=True,
            )
            sent = True
        except Exception:
            logger.warning("Envoi e-mail vérification ignoré", exc_info=True)
            sent = False
    notify_email_verification(user=user, email=email, purpose=purpose)
    return raw, sent


def verify_email(*, token: str) -> None:
    """REGISTER : verified_at seulement. EMAIL_CHANGE : pose users.email. Replay 200."""
    digest = hash_email_token(token)
    row = EmailVerification.objects.filter(token_hash=digest).select_related("user").first()
    if row is None:
        raise AuthAPIError(400, "INVALID_TOKEN", MSG_INVALID_TOKEN)
    if row.verified_at is not None:
        return
    if row.revoked_at is not None or row.expires_at <= timezone.now():
        raise AuthAPIError(400, "INVALID_TOKEN", MSG_INVALID_TOKEN)
    now = timezone.now()
    if row.purpose == EmailVerification.Purpose.EMAIL_CHANGE:
        taken = User.objects.filter(email=row.email).exclude(pk=row.user_id).exists()
        if taken:
            raise AuthAPIError(409, "CONFLICT", MSG_CONFLICT)
        user = row.user
        user.email = row.email
        user.save(update_fields=["email", "updated_at"])
    row.verified_at = now
    row.save(update_fields=["verified_at"])


def request_email_change(*, user: User, email: str, ip=None) -> None:
    """202 côté vue. users.email inchangé tant que le token n’est pas vérifié."""
    if user.ldap_dn:
        raise AuthAPIError(400, "EMAIL_CHANGE_FORBIDDEN", MSG_FORBIDDEN)
    email = email.strip().lower()
    if email == user.email:
        raise AuthAPIError(400, "EMAIL_UNCHANGED", MSG_UNCHANGED)
    if User.objects.filter(email=email).exists():
        raise AuthAPIError(409, "CONFLICT", MSG_CONFLICT)
    issue_email_verification(
        user,
        email=email,
        purpose=EmailVerification.Purpose.EMAIL_CHANGE,
    )


def resend_email_change(*, user: User, ip=None) -> None:
    """Dernier EMAIL_CHANGE unused. 429 au-delà du plafond."""
    if rate_limit_service.is_email_resend_limited(user.id, ip):
        raise AuthAPIError(429, "EMAIL_RESEND_RATE_LIMITED", MSG_RESEND_LIMIT)
    rate_limit_service.email_resend_hit(user.id, ip)
    pending = (
        EmailVerification.objects.filter(
            user=user,
            purpose=EmailVerification.Purpose.EMAIL_CHANGE,
            verified_at__isnull=True,
            revoked_at__isnull=True,
        )
        .order_by("-created_at")
        .first()
    )
    if pending is None:
        raise AuthAPIError(400, "INVALID_TOKEN", MSG_NO_PENDING)
    issue_email_verification(
        user,
        email=pending.email,
        purpose=EmailVerification.Purpose.EMAIL_CHANGE,
    )
