"""AUTH-E : alerte nouvel appareil. Pas d’app notifications (NOTIF-A plus tard)."""

import logging

logger = logging.getLogger(__name__)


def emit_device_new(*, user, device) -> None:
    """Stub : log seulement. NOTIF-A poussera FCM vers les autres appareils."""
    logger.info("DEVICE_NEW user=%s device=%s uuid=%s", user.id, device.id, device.device_uuid)
