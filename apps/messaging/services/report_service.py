"""MESSAGERIE-F : signalement de message et modération admin (MSG-93…98)."""

from datetime import timedelta

from django.utils import timezone

from apps.iam.exceptions import AuthAPIError
from apps.messaging.models import Message, ReportedMessage
from apps.messaging.services import conversation_service

MSG_NOT_FOUND = "Message ou signalement introuvable."
MSG_VALIDATION = "Paramètre invalide."
MSG_RATE_LIMITED = "Trop de signalements aujourd'hui."

_DAILY_LIMIT = 10
_WINDOW = timedelta(hours=24)


def create_report(*, user, message_id, reason: str) -> dict:
    reason = (reason or "").strip()
    if not reason:
        raise AuthAPIError(400, "VALIDATION_ERROR", MSG_VALIDATION, extra={"field": "reason"})
    try:
        message = Message.objects.get(pk=message_id)
    except (Message.DoesNotExist, ValueError, TypeError) as exc:
        raise AuthAPIError(404, "NOT_FOUND", MSG_NOT_FOUND) from exc
    conversation_service.get_member_or_404(user, conversation_id=message.conversation_id)

    cutoff = timezone.now() - _WINDOW
    recent = ReportedMessage.objects.filter(reported_by=user, created_at__gte=cutoff).count()
    if recent >= _DAILY_LIMIT:
        raise AuthAPIError(429, "REPORT_RATE_LIMITED", MSG_RATE_LIMITED)

    report = ReportedMessage.objects.create(message=message, reason=reason, reported_by=user)
    return {"id": str(report.id), "status": report.status}


def list_reports(*, status=None) -> dict:
    qs = ReportedMessage.objects.select_related("reported_by").order_by("-created_at")
    qs = qs.filter(status=status or ReportedMessage.Status.PENDING)
    return {
        "results": [
            {
                "id": str(r.id),
                "message_id": str(r.message_id),
                "reason": r.reason,
                "status": r.status,
                "reported_by": str(r.reported_by_id) if r.reported_by_id else None,
                "created_at": r.created_at.isoformat(),
            }
            for r in qs
        ]
    }


def review_report(*, user, report_id, status: str, note: str = "") -> dict:
    """`note` accepté pour compat contrat métier — pas de colonne dédiée sur ReportedMessage."""
    if status not in ReportedMessage.Status.values:
        raise AuthAPIError(400, "VALIDATION_ERROR", MSG_VALIDATION, extra={"field": "status"})
    try:
        report = ReportedMessage.objects.get(pk=report_id)
    except (ReportedMessage.DoesNotExist, ValueError, TypeError) as exc:
        raise AuthAPIError(404, "NOT_FOUND", MSG_NOT_FOUND) from exc
    report.status = status
    report.reviewed_by = user
    report.reviewed_at = timezone.now()
    report.save(update_fields=["status", "reviewed_by", "reviewed_at"])
    return {
        "id": str(report.id),
        "status": report.status,
        "reviewed_at": report.reviewed_at.isoformat(),
    }
