"""Template context: unread notification count for authenticated users."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def notifications_badge(request):
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return {"notif_unread": 0}
    try:
        from .services import unread_count

        return {"notif_unread": unread_count(request.user)}
    except Exception:
        logger.exception("notifications_badge failed for user_id=%s", getattr(request.user, "pk", None))
        return {"notif_unread": 0}
