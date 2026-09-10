"""AUTH-I : liste historique de connexions (owner / admin). Jamais de hash."""

from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.iam.exceptions import AuthAPIError
from apps.iam.models import LoginHistory, User

MSG_USER = "Utilisateur introuvable."


def parse_login_query(request) -> tuple[int, object | None]:
    """limit défaut 50 max 100 ; before = cursor created_at ISO."""
    raw_limit = request.query_params.get("limit")
    limit = 50
    if raw_limit not in (None, ""):
        try:
            limit = int(raw_limit)
        except (TypeError, ValueError) as exc:
            raise AuthAPIError(400, "VALIDATION_ERROR", "Paramètre limit invalide.") from exc
    limit = max(1, min(limit, 100))
    before = None
    raw_before = request.query_params.get("before")
    if raw_before:
        before = parse_datetime(raw_before)
        if before is None:
            raise AuthAPIError(400, "VALIDATION_ERROR", "Paramètre before invalide.")
        if timezone.is_naive(before):
            before = timezone.make_aware(before, timezone.utc)
    return limit, before


def serialize_login(row: LoginHistory) -> dict:
    device = row.device
    return {
        "id": str(row.id),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "success": row.success,
        "suspicious": row.suspicious,
        "ip_address": row.ip_address,
        "country": row.country,
        "city": row.city,
        "device_id": str(device.id) if device is not None else None,
        "device_name": device.device_name if device is not None else None,
        "platform": device.platform if device is not None else None,
        "browser": row.browser,
        "login_method": row.login_method,
        "failure_reason": row.failure_reason,
    }


def list_logins(*, user: User, limit: int, before=None) -> list[dict]:
    qs = LoginHistory.objects.filter(user=user).select_related("device").order_by("-created_at")
    if before is not None:
        qs = qs.filter(created_at__lt=before)
    return [serialize_login(row) for row in qs[:limit]]


def get_user_or_404(user_id) -> User:
    try:
        return User.objects.get(pk=user_id)
    except User.DoesNotExist as exc:
        raise AuthAPIError(404, "NOT_FOUND", MSG_USER) from exc
