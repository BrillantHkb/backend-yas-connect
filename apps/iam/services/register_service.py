"""Inscription AUTH-D : check-ad, register/ad, hors AD, verify-email, approve/reject."""

from __future__ import annotations

import logging
import re
import unicodedata
import uuid

from django.db import models

from apps.annuaire.models import Segment
from apps.iam.exceptions import AuthAPIError
from apps.iam.models import AuditLog, EmailVerification, LoginMethod, Region, Role, User
from apps.iam.services import rate_limit_service
from apps.iam.services.auth_service import MSG_INVALID
from apps.iam.services.email_verification_service import issue_email_verification
from apps.iam.services.email_verification_service import verify_email as verify_email_token
from apps.iam.services.ldap_service import (
    AdIdentity,
    DirectoryUnavailable,
    LdapBindFailed,
    bind_user_dn,
    search_user_dn,
    search_user_identity,
)
from apps.iam.services.password_policy import enforce_password_policy
from apps.iam.services.password_service import verify_dummy

logger = logging.getLogger(__name__)

MSG_AD_EXISTS = "Utilisez l’inscription Active Directory."
MSG_CONFLICT = "Compte déjà existant."
MSG_PENDING_CREATED = "Compte créé. Validation requise avant connexion."


def _audit(
    *,
    action: str,
    user: User | None,
    entity_id,
    old=None,
    new=None,
    metadata=None,
    ip=None,
    actor=None,
    severity="INFO",
):
    """Écriture audit IAM. Pas de MDP / token clair dans metadata."""
    AuditLog.objects.create(
        trace_id=uuid.uuid4(),
        module="IAM",
        action=action,
        entity_type="users",
        entity_id=entity_id,
        old_values=old,
        new_values=new,
        metadata=metadata,
        ip_address=ip,
        severity=severity,
        success=True,
        user=actor,
    )


def _validate_region_segment(*, region_id, segment_id) -> tuple[Region, Segment]:
    """Obligatoires D02/D03. 400 métier (pas 404) pour ne pas leak l’existence."""
    try:
        region = Region.objects.get(pk=region_id)
    except Region.DoesNotExist as exc:
        raise AuthAPIError(400, "REGION_INVALID", "Région invalide.") from exc
    try:
        segment = Segment.objects.get(pk=segment_id, is_active=True)
    except Segment.DoesNotExist as exc:
        raise AuthAPIError(400, "SEGMENT_INVALID", "Segment invalide.") from exc
    return region, segment


def suggest_username(first_name: str, last_name: str) -> str:
    """D03 : jdupont, collision → jdupont2. Accents / non-alnum retirés."""
    def norm(s: str) -> str:
        s = unicodedata.normalize("NFKD", s)
        s = "".join(c for c in s if not unicodedata.combining(c))
        return re.sub(r"[^a-z0-9]", "", s.lower())

    base = (norm(first_name)[:1] + norm(last_name))[:64] or "user"
    candidate = base
    n = 2
    while User.objects.filter(username=candidate).exists():
        suffix = str(n)
        candidate = f"{base[: 64 - len(suffix)]}{suffix}"
        n += 1
    return candidate


def _issue_email_verification(user: User) -> tuple[str, bool]:
    """D04 : ticket REGISTER. Délègue au service AUTH-I."""
    return issue_email_verification(
        user,
        email=user.email,
        purpose=EmailVerification.Purpose.REGISTER,
    )


def check_ad(*, email, username, password, ip) -> dict:
    """D01 : jamais 401. 200 ad_available true|false ; 503 si AD down."""
    ident_key = f"register_ad:{email or username}"
    if rate_limit_service.is_limited(ident_key) or rate_limit_service.is_limited_ip(ip):
        return {"ad_available": False}  # contrat D01 : pas de 401
    rate_limit_service.hit(ident_key, ip)

    try:
        identity = search_user_identity(email=email, username=username)
        bind_user_dn(dn=identity.dn, password=password)
    except DirectoryUnavailable as exc:
        raise AuthAPIError(503, "DIRECTORY_UNAVAILABLE", "Annuaire indisponible.") from exc
    except LdapBindFailed:
        verify_dummy(password)  # timing ; réponse neutre
        return {"ad_available": False}
    return {"ad_available": True}


def register_ad(
    *,
    email,
    username,
    password_ad,
    password,
    profile: dict,
    device_spec: dict,
    ip,
    user_agent: str,
) -> dict:
    """D02 : search+bind, crée le user, begin_mfa (pas de JWT)."""
    ident_key = email or username
    rate_key = f"register_ad:{ident_key}"
    if rate_limit_service.is_limited(rate_key) or rate_limit_service.is_limited_ip(ip):
        raise AuthAPIError(401, "INVALID_CREDENTIALS", MSG_INVALID)
    rate_limit_service.hit(rate_key, ip)

    enforce_password_policy(password, email=email or "", username=username or "")
    region, segment = _validate_region_segment(
        region_id=profile["region_id"],
        segment_id=profile["segment_id"],
    )

    try:
        identity: AdIdentity = search_user_identity(email=email, username=username)
        bind_user_dn(dn=identity.dn, password=password_ad)  # preuve AD, jamais stockée
    except DirectoryUnavailable as exc:
        raise AuthAPIError(503, "DIRECTORY_UNAVAILABLE", "Annuaire indisponible.") from exc
    except LdapBindFailed as exc:
        raise AuthAPIError(401, "INVALID_CREDENTIALS", MSG_INVALID) from exc

    if User.objects.filter(
        models.Q(email=identity.upn.lower()) | models.Q(username=identity.sam)
    ).exists():
        raise AuthAPIError(409, "CONFLICT", MSG_CONFLICT)

    role = Role.objects.get(code="USER")
    user = User.objects.create_user(
        email=identity.upn,  # UPN AD, pas l’email du formulaire
        password=password,  # MDP app distinct (Argon2)
        username=identity.sam,  # sAMAccountName AD
        role=role,
        first_name=profile["first_name"],
        last_name=profile["last_name"],
        phone=profile["phone"],
        job_title=profile["job_title"],
        language=profile.get("language") or "fr",
        region=region,
        segment_id=segment.id,
        matricule=profile.get("matricule") or None,
        avatar_id=profile.get("avatar_id"),
        ldap_dn=identity.dn,  # lien sync AUTH-16 immédiat
        pending_approval=False,
        is_active=True,
    )
    prefs = user.preferences
    prefs.language = user.language
    prefs.save(update_fields=["language", "last_updated"])

    _audit(
        action="USER_REGISTER_AD",
        user=user,
        entity_id=user.id,
        new={"email": user.email, "username": user.username},
        metadata={"ldap_dn": user.ldap_dn},
        ip=ip,
        actor=user,
    )
    # AUTH-C : même challenge que login (enroll pour un compte neuf)
    from apps.iam.services.mfa_service import begin_mfa

    return begin_mfa(
        user=user,
        ip=ip,
        user_agent=user_agent,
        device_spec=device_spec,
        ident_key=user.email,
        login_method=LoginMethod.PASSWORD,
    )


def register_local(*, email, password, profile: dict, ip) -> dict:
    """D03 : hors AD, pending RH, 201 sans JWT."""
    email = email.strip().lower()
    enforce_password_policy(password, email=email, username="")
    region, segment = _validate_region_segment(
        region_id=profile["region_id"],
        segment_id=profile["segment_id"],
    )
    if User.objects.filter(email=email).exists():
        raise AuthAPIError(409, "CONFLICT", MSG_CONFLICT)

    try:
        search_user_dn(email=email, username=None)  # sans bind user
        raise AuthAPIError(409, "AD_ACCOUNT_EXISTS", MSG_AD_EXISTS)
    except DirectoryUnavailable:
        logger.warning("AD indisponible pendant register local — inscription locale continue")
    except LdapBindFailed:
        pass  # absent / non loggable → parcours hors AD OK

    username = suggest_username(profile["first_name"], profile["last_name"])
    role = Role.objects.get(code="USER")
    user = User.objects.create_user(
        email=email,
        password=password,
        username=username,
        role=role,
        first_name=profile["first_name"],
        last_name=profile["last_name"],
        phone=profile["phone"],
        job_title=profile["job_title"],
        language=profile.get("language") or "fr",
        region=region,
        segment_id=segment.id,
        matricule=profile.get("matricule") or None,
        avatar_id=profile.get("avatar_id"),
        ldap_dn=None,
        pending_approval=True,  # 403 ACCOUNT_PENDING jusqu’à D05
        is_active=False,
    )
    prefs = user.preferences
    prefs.language = user.language
    prefs.save(update_fields=["language", "last_updated"])

    _, sent = _issue_email_verification(user)
    _audit(
        action="USER_REGISTER_LOCAL",
        user=user,
        entity_id=user.id,
        new={"email": user.email, "username": user.username},
        metadata={"pending_approval": True},
        ip=ip,
        actor=None,
    )
    return {
        "user_id": str(user.id),
        "username": user.username,
        "email_verification_sent": sent,
    }


def verify_email(*, token: str) -> None:
    """D04 / AUTH-I : REGISTER ou EMAIL_CHANGE (même hash SHA-256)."""
    verify_email_token(token=token)


def resend_verification(*, email: str, ip) -> None:
    """Toujours silencieux si e-mail inconnu (anti-énumération)."""
    ident_key = f"register_resend:{email.strip().lower()}"
    if rate_limit_service.is_limited(ident_key) or rate_limit_service.is_limited_ip(ip):
        raise AuthAPIError(401, "INVALID_CREDENTIALS", MSG_INVALID)
    rate_limit_service.hit(ident_key, ip)
    user = User.objects.filter(
        email=email.strip().lower(),
        is_active=False,
        ldap_dn__isnull=True,
    ).first()
    if user is None:
        return  # anti-énumération : toujours 200 côté vue
    _issue_email_verification(user)


def list_users(*, request=None, pending_only: bool = False) -> dict:
    """Délègue ADM-01 (filtres + champs étendus). pending_only = file D05."""
    from apps.iam.services.admin_user_service import list_users as _list

    return _list(request=request, pending_only=pending_only)


def list_pending_users() -> dict:
    """File RH D05 (alias pending_only)."""
    return list_users(pending_only=True)


def approve_user(*, user_id, actor: User, ip) -> None:
    """D05 : active le hors-AD. Compte ldap_dn → 400 LDAP_MANAGED."""
    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist as exc:
        raise AuthAPIError(404, "NOT_FOUND", "Utilisateur introuvable.") from exc
    if user.ldap_dn:
        raise AuthAPIError(400, "LDAP_MANAGED", "Compte lié à Active Directory.")
    if user.is_active and not user.pending_approval:
        return  # idempotent
    old = {"is_active": user.is_active, "pending_approval": user.pending_approval}
    user.is_active = True
    user.pending_approval = False
    user.save(update_fields=["is_active", "pending_approval", "updated_at"])
    _audit(
        action="USER_APPROVE",
        user=user,
        entity_id=user.id,
        old=old,
        new={"is_active": True, "pending_approval": False},
        ip=ip,
        actor=actor,
    )


def reject_user(*, user_id, reason: str, actor: User, ip) -> None:
    """D05 : reste inactif. Motif audit seulement (pas dans la réponse HTTP)."""
    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist as exc:
        raise AuthAPIError(404, "NOT_FOUND", "Utilisateur introuvable.") from exc
    if user.ldap_dn:
        raise AuthAPIError(400, "LDAP_MANAGED", "Compte lié à Active Directory.")
    # Reste inactif ; le motif n’est pas exposé au client, seulement dans l’audit.
    _audit(
        action="USER_REJECT",
        user=user,
        entity_id=user.id,
        old={"is_active": user.is_active, "pending_approval": user.pending_approval},
        new={"is_active": user.is_active, "pending_approval": user.pending_approval},
        metadata={"reason": reason},
        ip=ip,
        actor=actor,
        severity="WARNING",
    )
