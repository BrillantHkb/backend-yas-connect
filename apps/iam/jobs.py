"""AUTH-16 LDAP + AUTH-H session_reaper + AUTH-I account_unlock_reaper."""

import uuid

from apps.iam.models import AuditLog, User
from apps.iam.services.ldap_service import iter_ad_logon_state
from apps.iam.services.session_service import reap_sessions as _reap_sessions


def sync_ldap_accounts() -> None:
    """Lève DirectoryUnavailable si AD down — le runner marque ERROR, aucune coupure de masse."""
    state = iter_ad_logon_state()  # dn → USABLE | DISABLED | …
    qs = User.objects.exclude(ldap_dn__isnull=True).exclude(ldap_dn="")
    for user in qs.iterator():
        status = state.get(user.ldap_dn)  # None = DN plus dans le search_base
        usable = status == "USABLE"
        reason = "DN_MISSING" if status is None else status
        if not usable and user.is_active:
            user.is_active = False  # coupe aussi le login MDP app
            user.save(update_fields=["is_active", "updated_at"])
            _audit(user, "USER_LDAP_DISABLE", old=True, new=False, reason=reason)
        elif usable and (not user.is_active) and (not user.is_locked):
            # lockout AD temporaire levé ; is_locked YAS reste prioritaire
            user.is_active = True
            user.save(update_fields=["is_active", "updated_at"])
            _audit(user, "USER_LDAP_ENABLE", old=False, new=True, reason="USABLE")


def reap_sessions() -> int:
    """AUTH-H : INACTIVITY / EXPIRED. Handler scheduled_jobs session_reaper."""
    return _reap_sessions()


def unlock_expired_locks() -> int:
    """AUTH-I : is_locked et locked_at + TTL ≤ now. Handler account_unlock_reaper."""
    from apps.iam.services.lock_service import unlock_expired

    return unlock_expired()


def _audit(user, action: str, *, old: bool, new: bool, reason: str) -> None:
    """Job système : user=None (pas un admin humain)."""
    AuditLog.objects.create(
        trace_id=uuid.uuid4(),
        module="IAM",
        action=action,
        entity_type="users",
        entity_id=user.id,
        old_values={"is_active": old},
        new_values={"is_active": new},
        metadata={"ldap_dn": user.ldap_dn, "reason": reason},
        severity="WARNING" if action.endswith("DISABLE") else "INFO",
        success=True,
        user=None,  # pas d’acteur humain
    )
