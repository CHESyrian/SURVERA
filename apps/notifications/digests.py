"""Email digests — periodic summary of unread in-app notifications."""
from __future__ import annotations

import logging
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.notifications.email import absolute_url, send_notification_email
from apps.notifications.models import Notification
from apps.notifications.preferences import NotificationPreference

logger = logging.getLogger(__name__)
User = get_user_model()

DIGEST_MAX_ITEMS = 15


def users_due_for_digest(*, frequency: str) -> list:
    """
    Return users whose digest preference matches frequency and who are due.

    Daily: not sent in last 20 hours (or never).
    Weekly: not sent in last 6 days (or never).
    """
    now = timezone.now()
    if frequency == NotificationPreference.DigestFrequency.DAILY:
        cutoff = now - timedelta(hours=20)
    elif frequency == NotificationPreference.DigestFrequency.WEEKLY:
        cutoff = now - timedelta(days=6)
    else:
        return []

    due = Q(notification_prefs__last_digest_sent_at__isnull=True) | Q(
        notification_prefs__last_digest_sent_at__lt=cutoff
    )
    users = list(
        User.objects.filter(
            is_active=True,
            closed_at__isnull=True,
            notification_prefs__email_digest=frequency,
        )
        .exclude(email="")
        .filter(due)
        .select_related("notification_prefs")[:500]
    )

    # Default for users with no prefs row is daily
    if frequency == NotificationPreference.DigestFrequency.DAILY:
        no_prefs = list(
            User.objects.filter(
                is_active=True,
                closed_at__isnull=True,
                notification_prefs__isnull=True,
            ).exclude(email="")[:200]
        )
        users.extend(no_prefs)
    return users


def collect_digest_items(user, *, limit: int = DIGEST_MAX_ITEMS) -> list[Notification]:
    """Unread notifications, newest first."""
    return list(
        Notification.objects.filter(user=user, read_at__isnull=True)
        .order_by("-created_at")[:limit]
    )


def send_digest_for_user(user, *, frequency: str | None = None) -> bool:
    """
    Build and send one digest email if there is unread content.
    Returns True if an email was sent.
    """
    prefs = NotificationPreference.objects.filter(user=user).first()
    freq = frequency or (
        prefs.email_digest
        if prefs
        else NotificationPreference.DigestFrequency.DAILY
    )
    if freq == NotificationPreference.DigestFrequency.OFF:
        return False

    items = collect_digest_items(user)
    if not items:
        return False

    unread_total = Notification.objects.filter(user=user, read_at__isnull=True).count()
    subject = _("SURVERA activity digest (%(n)d unread)") % {"n": unread_total}
    ok = send_notification_email(
        to_email=user.email,
        subject=subject,
        template_name="notifications/email/digest.html",
        context={
            "user": user,
            "items": items,
            "unread_total": unread_total,
            "frequency": freq,
            "inbox_url": absolute_url("/notifications/"),
        },
    )
    if ok:
        prefs_obj, _ = NotificationPreference.objects.get_or_create(user=user)
        prefs_obj.last_digest_sent_at = timezone.now()
        prefs_obj.save(update_fields=["last_digest_sent_at", "updated_at"])
    return ok


def run_digests(*, frequency: str) -> int:
    """Send digests for all due users. Returns number of emails sent."""
    sent = 0
    for user in users_due_for_digest(frequency=frequency):
        try:
            if send_digest_for_user(user, frequency=frequency):
                sent += 1
        except Exception:
            logger.exception("Digest failed for user_id=%s", getattr(user, "pk", None))
    return sent
