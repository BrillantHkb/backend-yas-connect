"""Orchestration login / refresh AUTH-A (AUTH-01 … 12). Les vues HTTP n’ont pas de métier."""

import uuid
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from apps.iam.exceptions import AuthAPIError
from apps.iam.models import LoginHistory, LoginMethod, RefreshToken, Session, User
from apps.iam.services import rate_limit_service
from apps.iam.services.device_service import (
    jailbreak_blocked,
    on_new_device,
    revoke_active_sessions_for_device,
    upsert_device,
)
from apps.iam.services.jti_blacklist import blacklist_jti
from apps.iam.services.password_service import verify_dummy, verify_password
from apps.iam.services.session_service import (
    revoke_sessions,
    session_absolute_seconds,
    session_dead,
)
from apps.iam.services.token_service import (
    hash_refresh_token,
    issue_refresh,
    sign_access_token,
)
from apps.iam.services.ua_service import parse_user_agent

# Message unique AUTH-05 : inconnu / MDP faux / rate-limit (pas d’énumération)
MSG_INVALID = "Identifiant ou mot de passe incorrect."


def client_ip(request) -> str | None:
    """IP client : 1er hop X-Forwarded-For si proxy, sinon REMOTE_ADDR."""
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def normalize_email(email: str) -> str:
    """Login toujours en minuscules (catalogue users.email)."""
    return email.strip().lower()


def public_user(user: User) -> dict:
    """Payload JSON 200 : profil + role + prefs/privacy. Jamais password / hash."""
    role = user.role
    prefs = getattr(user, "preferences", None)
    privacy = getattr(user, "privacy", None)
    return {
        "id": str(user.id),
        "email": user.email,
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "matricule": user.matricule,
        "phone": user.phone,
        "job_title": user.job_title,
        "status": user.status,  # présence ONLINE/OFFLINE, pas le statut de compte
        "language": user.language,
        "timezone": user.timezone,
        "role": {"id": str(role.id), "code": role.code, "name": role.name},
        "region_id": str(user.region_id) if user.region_id else None,
        "segment_id": str(user.segment_id) if user.segment_id else None,  # UUID sans FK
        "avatar_id": str(user.avatar_id) if user.avatar_id else None,
        "preferences": {
            "language": prefs.language,
            "timezone": prefs.timezone,
            "notification_sound": prefs.notification_sound,
            "auto_download_media": prefs.auto_download_media,
            "read_receipts": prefs.read_receipts,
            "typing_indicator": prefs.typing_indicator,
        }
        if prefs
        else None,
        "privacy": {
            "last_seen_visibility": privacy.last_seen_visibility,
            "profile_photo_visibility": privacy.profile_photo_visibility,
            "online_status_visibility": privacy.online_status_visibility,
            "read_receipts_enabled": privacy.read_receipts_enabled,
            "typing_indicator_enabled": privacy.typing_indicator_enabled,
            "allow_calls": privacy.allow_calls,
            "allow_mentions": privacy.allow_mentions,
            "allow_group_invites": privacy.allow_group_invites,
        }
        if privacy
        else None,
    }


def _get_user(*, email: str | None, username: str | None) -> User | None:
    """Lookup AUTH-01/02. Prefetch role/prefs/privacy pour le JSON 200."""
    qs = User.objects.select_related("role", "preferences", "privacy")
    try:
        if email:
            return qs.get(email=email)  # déjà normalisé en lower
        if not settings.YAS_LOGIN_ALLOW_USERNAME:
            return None  # username interdit → dummy + 401 (pas 400)
        return qs.get(username__iexact=username)
    except User.DoesNotExist:
        return None


def _history(
    *,
    user,
    email: str,
    ip,
    success: bool,
    reason=None,
    user_agent: str = "",
    session=None,
    device=None,
    login_method=LoginMethod.PASSWORD,
    suspicious: bool = False,
) -> LoginHistory:
    """INSERT login_history. device_id seulement au succès (pas d’upsert device avant MDP OK)."""
    browser, browser_version = parse_user_agent(user_agent)
    return LoginHistory.objects.create(
        user=user,  # NULL si identifiant inconnu
        device=device,
        session=session,
        email=email,  # identifiant tenté (email ou username)
        ip_address=ip,
        browser=browser,
        browser_version=browser_version,
        login_method=login_method,
        success=success,
        suspicious=suspicious,  # AUTH-29 : 1er UUID
        failure_reason=reason,  # NULL si succès
    )


def _guard_login_rate_limit(*, ident_key, ip, user_agent, skip_ident: bool, login_method) -> None:
    """AUTH-06. skip_ident si user déjà locké (sinon 403 ACCOUNT_LOCKED jamais atteint)."""
    ident_blocked = (not skip_ident) and rate_limit_service.is_limited(ident_key)
    if ident_blocked or rate_limit_service.is_limited_ip(ip):
        _history(
            user=None,
            email=ident_key,
            ip=ip,
            success=False,
            reason="RATE_LIMITED",
            user_agent=user_agent,
            login_method=login_method,
        )
        raise AuthAPIError(401, "INVALID_CREDENTIALS", MSG_INVALID)
    rate_limit_service.hit(ident_key, ip)


def login(*, email, username, password, ip, user_agent: str, device_spec: dict) -> dict:
    """Ordre AUTH-I : lookup → rate-limit (skip ident si locké) → MDP → lazy_unlock → 403 → MFA."""
    from apps.iam.services.lock_service import lazy_unlock, maybe_lock_after_failure

    email = normalize_email(email) if email else None
    username = username.strip() if username else None

    ident_key = email or username  # un seul identifiant (le serializer a déjà validé)
    user = _get_user(email=email, username=username)
    _guard_login_rate_limit(
        ident_key=ident_key,
        ip=ip,
        user_agent=user_agent,
        skip_ident=bool(user is not None and user.is_locked),
        login_method=LoginMethod.PASSWORD,
    )

    if user is None:
        verify_dummy(password)  # AUTH-05 : même durée qu’un check Argon2 réel
        _history(
            user=None,
            email=ident_key,
            ip=ip,
            success=False,
            reason="INVALID_CREDENTIALS",
            user_agent=user_agent,
        )
        raise AuthAPIError(401, "INVALID_CREDENTIALS", MSG_INVALID)

    if not verify_password(password, user.password):
        _history(
            user=user,
            email=user.email,  # user connu : on journalise l’email réel
            ip=ip,
            success=False,
            reason="INVALID_CREDENTIALS",
            user_agent=user_agent,
        )
        maybe_lock_after_failure(user)
        raise AuthAPIError(401, "INVALID_CREDENTIALS", MSG_INVALID)

    # AUTH-03 / 04 : 403 seulement après MDP OK
    if user.pending_approval:
        _history(
            user=user,
            email=user.email,
            ip=ip,
            success=False,
            reason="ACCOUNT_PENDING",
            user_agent=user_agent,
        )
        raise AuthAPIError(403, "ACCOUNT_PENDING", "Compte en attente de validation.")

    if not user.is_active:
        _history(
            user=user,
            email=user.email,
            ip=ip,
            success=False,
            reason="ACCOUNT_DISABLED",
            user_agent=user_agent,
        )
        raise AuthAPIError(403, "ACCOUNT_DISABLED", "Compte désactivé.")

    lazy_unlock(user)
    if user.is_locked:
        _history(
            user=user,
            email=user.email,
            ip=ip,
            success=False,
            reason="ACCOUNT_LOCKED",
            user_agent=user_agent,
        )
        raise AuthAPIError(403, "ACCOUNT_LOCKED", "Compte verrouillé.")

    # AUTH-C : JWT seulement après POST /mfa/verify
    from apps.iam.services.mfa_service import begin_mfa

    return begin_mfa(
        user=user,
        ip=ip,
        user_agent=user_agent,
        device_spec=device_spec,
        ident_key=ident_key,
        login_method=LoginMethod.PASSWORD,
    )


def login_ldap(*, email, username, password, ip, user_agent: str, device_spec: dict) -> dict:
    """AUTH-13 : bind AD, user YAS déjà en base, puis begin_mfa. Pas de JIT."""
    # Import local : ldap3 n’est chargé que sur le chemin LDAP (tests mockent ldap_service).
    from apps.iam.services.ldap_service import (
        DirectoryUnavailable,
        LdapBindFailed,
        bind_user_dn,
        search_user_dn,
    )

    email = normalize_email(email) if email else None
    username = username.strip() if username else None

    ident_key = email or username
    user = _get_user(email=email, username=username)
    _guard_login_rate_limit(
        ident_key=ident_key,
        ip=ip,
        user_agent=user_agent,
        skip_ident=bool(user is not None and user.is_locked),
        login_method=LoginMethod.LDAP,
    )

    if user is None:
        verify_dummy(password)  # timing AUTH-05 ; on ne contacte pas l’AD
        _history(
            user=None,
            email=ident_key,
            ip=ip,
            success=False,
            reason="INVALID_CREDENTIALS",
            user_agent=user_agent,
            login_method=LoginMethod.LDAP,
        )
        raise AuthAPIError(401, "INVALID_CREDENTIALS", MSG_INVALID)

    try:
        if user.ldap_dn:
            try:
                bind_user_dn(dn=user.ldap_dn, password=password)
                dn = user.ldap_dn
            except LdapBindFailed:
                # DN déplacé ou compte devenu non loggable : un retry search+bind
                dn = search_user_dn(email=user.email, username=user.username)
                bind_user_dn(dn=dn, password=password)
                # ne pas écraser ldap_dn : AUTH-16 s’appuie sur la valeur liée
        else:
            dn = search_user_dn(email=user.email, username=user.username)
            bind_user_dn(dn=dn, password=password)
    except DirectoryUnavailable as exc:
        _history(
            user=user,
            email=user.email,
            ip=ip,
            success=False,
            reason="DIRECTORY_UNAVAILABLE",
            user_agent=user_agent,
            login_method=LoginMethod.LDAP,
        )
        raise AuthAPIError(503, "DIRECTORY_UNAVAILABLE", "Annuaire indisponible.") from exc
    except LdapBindFailed as exc:
        _history(
            user=user,
            email=user.email,
            ip=ip,
            success=False,
            reason="INVALID_CREDENTIALS",
            user_agent=user_agent,
            login_method=LoginMethod.LDAP,
        )
        from apps.iam.services.lock_service import maybe_lock_after_failure

        maybe_lock_after_failure(user)
        raise AuthAPIError(401, "INVALID_CREDENTIALS", MSG_INVALID) from exc

    # 403 YAS seulement après bind AD OK (pas les bits UAC)
    if user.pending_approval:
        _history(
            user=user,
            email=user.email,
            ip=ip,
            success=False,
            reason="ACCOUNT_PENDING",
            user_agent=user_agent,
            login_method=LoginMethod.LDAP,
        )
        raise AuthAPIError(403, "ACCOUNT_PENDING", "Compte en attente de validation.")

    if not user.is_active:
        _history(
            user=user,
            email=user.email,
            ip=ip,
            success=False,
            reason="ACCOUNT_DISABLED",
            user_agent=user_agent,
            login_method=LoginMethod.LDAP,
        )
        raise AuthAPIError(403, "ACCOUNT_DISABLED", "Compte désactivé.")

    from apps.iam.services.lock_service import lazy_unlock

    lazy_unlock(user)
    if user.is_locked:
        _history(
            user=user,
            email=user.email,
            ip=ip,
            success=False,
            reason="ACCOUNT_LOCKED",
            user_agent=user_agent,
            login_method=LoginMethod.LDAP,
        )
        raise AuthAPIError(403, "ACCOUNT_LOCKED", "Compte verrouillé.")

    if not user.ldap_dn:
        user.ldap_dn = dn  # 1er lien YAS ↔ DN (D02 l’a déjà en général)
        user.save(update_fields=["ldap_dn", "updated_at"])

    # AUTH-C : JWT seulement après POST /mfa/verify (login_method=LDAP)
    from apps.iam.services.mfa_service import begin_mfa

    return begin_mfa(
        user=user,
        ip=ip,
        user_agent=user_agent,
        device_spec=device_spec,
        ident_key=ident_key,
        login_method=LoginMethod.LDAP,
    )


def complete_login(*, user, ip, user_agent, device_spec, ident_key, login_method) -> dict:
    """Queue : upsert → 403 appareil → DEVICE_NEW → session JWT."""
    device, created = upsert_device(user=user, spec=device_spec, ip=ip)  # AUTH-11 + 32

    if device.compromised:
        _history(
            user=user,
            email=user.email,
            ip=ip,
            success=False,
            reason="DEVICE_COMPROMISED",
            user_agent=user_agent,
            device=device,
            login_method=login_method,
        )
        raise AuthAPIError(403, "DEVICE_COMPROMISED", "Appareil signalé compromis.")

    if jailbreak_blocked(device=device):
        _history(
            user=user,
            email=user.email,
            ip=ip,
            success=False,
            reason="DEVICE_JAILBROKEN",
            user_agent=user_agent,
            device=device,
            login_method=login_method,
        )
        raise AuthAPIError(403, "DEVICE_JAILBROKEN", "Appareil non autorisé (root/jailbreak).")

    if created:
        on_new_device(user=user, device=device, ip=ip)  # AUTH-29 : alerte, pas de MFA extra

    revoke_active_sessions_for_device(device=device)  # AUTH-12

    now = timezone.now()
    access_jti = uuid.uuid4()  # = jti du JWT
    refresh_jti = uuid.uuid4()
    session = Session.objects.create(
        user=user,
        device=device,  # NOT NULL au succès login local
        access_jti=access_jti,
        refresh_jti=refresh_jti,
        ip_address=ip,
        user_agent=user_agent or "",
        last_activity=now,
        expires_at=now + timedelta(seconds=session_absolute_seconds()),
        is_active=True,
        login_method=login_method,
    )
    raw_refresh = issue_refresh(session=session, user=user, ip=ip)  # AUTH-10

    user.last_login = now  # AUTH-08
    if user.first_login is None:
        user.first_login = now  # 1er succès seulement
    user.save(update_fields=["last_login", "first_login", "updated_at"])

    row = _history(
        user=user,
        email=user.email,
        ip=ip,
        success=True,
        session=session,
        user_agent=user_agent,
        device=device,
        login_method=login_method,
        suspicious=created,  # AUTH-29 : 1er uuid seulement
    )
    from apps.iam.services.geo_service import lookup as lookup_geo
    from apps.iam.services.lock_service import mark_suspicious

    geo = lookup_geo(ip)
    if geo:
        country = geo.get("country")
        city = geo.get("city")
        if country or city:
            row.country = country
            row.city = city
            row.save(update_fields=["country", "city"])
    mark_suspicious(history=row)
    rate_limit_service.reset(ident_key)  # succès : on oublie les échecs de cet identifiant

    token = sign_access_token(
        user_id=user.id,
        email=user.email,
        role_id=user.role_id,
        role_code=user.role.code,
        jti=access_jti,
    )
    return {
        "access_token": token,
        "refresh_token": raw_refresh,  # une seule fois
        "token_type": "Bearer",
        "expires_in": settings.YAS_JWT_ACCESS_TTL_SECONDS,
        "refresh_expires_in": settings.YAS_JWT_REFRESH_TTL_SECONDS,
        "user": public_user(user),
    }


def _force_logout_user(*, user, reason: str, except_session_id=None) -> None:
    """Tue les sessions actives (+ refresh + JTI). AUTH-43 : except_session_id = courante."""
    revoke_sessions(user=user, reason=reason, except_session_id=except_session_id)


def refresh(*, raw: str, ip) -> dict:
    """Rotation AUTH-10 / AUTH-H : nouvel access + refresh. Ancien hash = ROTATED."""
    digest = hash_refresh_token(raw)
    row = (
        RefreshToken.objects.select_related(
            "session", "user", "user__role", "user__preferences", "user__privacy"
        )
        .filter(token_hash=digest)
        .first()
    )
    if row is None:
        raise AuthAPIError(401, "INVALID_REFRESH", "Session expirée. Reconnectez-vous.")
    # Réutilisation d’un token déjà rotaté / révoqué = vol → kill global
    if row.revoked_at is not None or row.rotated_at is not None:
        _force_logout_user(user=row.user, reason="REFRESH_REUSE")
        raise AuthAPIError(401, "FORCE_LOGOUT", "Session invalidée. Reconnectez-vous.")

    now = timezone.now()
    session = row.session
    if session_dead(session, now) or row.expires_at <= now:
        raise AuthAPIError(401, "INVALID_REFRESH", "Session expirée. Reconnectez-vous.")

    blacklist_jti(session.access_jti, ttl=settings.YAS_JWT_ACCESS_TTL_SECONDS)

    row.rotated_at = now
    row.revoked_at = now
    row.revoked_reason = "ROTATED"
    row.save(update_fields=["rotated_at", "revoked_at", "revoked_reason"])

    access_jti = uuid.uuid4()
    refresh_jti = uuid.uuid4()
    session.access_jti = access_jti  # l’ancien JWT access ne matche plus access_jti
    session.refresh_jti = refresh_jti
    session.last_activity = now
    session.save(update_fields=["access_jti", "refresh_jti", "last_activity", "updated_at"])
    new_raw = issue_refresh(session=session, user=session.user, ip=ip)
    token = sign_access_token(
        user_id=session.user.id,
        email=session.user.email,
        role_id=session.user.role_id,
        role_code=session.user.role.code,
        jti=access_jti,
    )
    return {
        "access_token": token,
        "refresh_token": new_raw,
        "token_type": "Bearer",
        "expires_in": settings.YAS_JWT_ACCESS_TTL_SECONDS,
        "refresh_expires_in": settings.YAS_JWT_REFRESH_TTL_SECONDS,
        "user": public_user(session.user),
    }
