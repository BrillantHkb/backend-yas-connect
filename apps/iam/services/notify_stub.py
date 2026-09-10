"""AUTH-E / AUTH-I : alertes stub. Pas d’app notifications (NOTIF-A plus tard)."""

import logging

logger = logging.getLogger(__name__)


def emit_device_new(*, user, device) -> None:
    """Stub : log seulement. NOTIF-A poussera FCM vers les autres appareils."""
    logger.info("DEVICE_NEW user=%s device=%s uuid=%s", user.id, device.id, device.device_uuid)


def notify_suspicious_login(*, user, history, previous_country: str) -> None:
    """AUTH-62 : log seulement. NOTIF-A poussera l’alerte réel."""
    logger.info(
        "LOGIN_NEW_COUNTRY user=%s history=%s from=%s to=%s",
        user.id,
        history.id,
        previous_country,
        history.country,
    )


def notify_email_verification(*, user, email: str, purpose: str) -> None:
    """AUTH-65/66 : log le lien (pas le token). SMTP réel = EMAIL_HOST si configuré."""
    logger.info(
        "EMAIL_VERIFICATION user=%s email=%s purpose=%s",
        user.id,
        email,
        purpose,
    )
