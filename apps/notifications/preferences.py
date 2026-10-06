"""Per-user notification channel preferences."""
from __future__ import annotations

from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _

from apps.common.models import TimeStampedModel

from .models import Notification


class NotificationPreference(TimeStampedModel):
    """
    Channel toggles per notification type.

    Default matrix for real users (also used when no row exists):

    | Type              | In-app | Email | Notes                                      |
    |-------------------|--------|-------|--------------------------------------------|
    | survey_published  | on     | on    | Email only for private / members_only      |
    | team_invite       | on     | on    | Actionable; keep email on                  |
    | points_awarded    | on     | off   | Frequent; avoid inbox noise                |
    | system            | on     | off   | Rare; in-app is enough by default          |
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notification_prefs",
    )

    # In-app — all on by default (low friction, user already in the product)
    inapp_survey_published = models.BooleanField(_("In-app: survey published"), default=True)
    inapp_points_awarded = models.BooleanField(_("In-app: points awarded"), default=True)
    inapp_team_invite = models.BooleanField(_("In-app: team invite"), default=True)
    inapp_system = models.BooleanField(_("In-app: system"), default=True)

    # Email — only high-intent / rare events on by default
    email_survey_published = models.BooleanField(
        _("Email: survey published"),
        default=True,
        help_text=_("Only sent for private or members-only surveys."),
    )
    email_points_awarded = models.BooleanField(
        _("Email: points awarded"),
        default=False,
        help_text=_("Off by default — points awards can be frequent."),
    )
    email_team_invite = models.BooleanField(
        _("Email: team invite"),
        default=True,
        help_text=_("On by default — user needs to know they were added."),
    )
    email_system = models.BooleanField(
        _("Email: system"),
        default=False,
        help_text=_("Off by default — system notices stay in-app unless opted in."),
    )

    class DigestFrequency(models.TextChoices):
        OFF = "off", _("Off")
        DAILY = "daily", _("Daily")
        WEEKLY = "weekly", _("Weekly")

    # Digest email — summary of recent in-app activity (not a substitute for invites)
    email_digest = models.CharField(
        _("Email digest"),
        max_length=10,
        choices=DigestFrequency.choices,
        default=DigestFrequency.DAILY,
        help_text=_("Periodic summary of unread notifications. Invites still send immediately."),
    )
    last_digest_sent_at = models.DateTimeField(
        _("last digest sent at"),
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = _("notification preference")
        verbose_name_plural = _("notification preferences")

    def __str__(self) -> str:
        return f"prefs:{self.user_id}"


# Defaults when no row exists
_DEFAULT_INAPP = {
    Notification.Type.SURVEY_PUBLISHED: True,
    Notification.Type.POINTS_AWARDED: True,
    Notification.Type.TEAM_INVITE: True,
    Notification.Type.SYSTEM: True,
}
_DEFAULT_EMAIL = {
    Notification.Type.SURVEY_PUBLISHED: True,
    Notification.Type.POINTS_AWARDED: False,
    Notification.Type.TEAM_INVITE: True,
    Notification.Type.SYSTEM: False,
}

_INAPP_ATTR = {
    Notification.Type.SURVEY_PUBLISHED: "inapp_survey_published",
    Notification.Type.POINTS_AWARDED: "inapp_points_awarded",
    Notification.Type.TEAM_INVITE: "inapp_team_invite",
    Notification.Type.SYSTEM: "inapp_system",
}
_EMAIL_ATTR = {
    Notification.Type.SURVEY_PUBLISHED: "email_survey_published",
    Notification.Type.POINTS_AWARDED: "email_points_awarded",
    Notification.Type.TEAM_INVITE: "email_team_invite",
    Notification.Type.SYSTEM: "email_system",
}


def get_or_create_preferences(user) -> NotificationPreference:
    prefs, _ = NotificationPreference.objects.get_or_create(user=user)
    return prefs


def wants_inapp(user, ntype: str) -> bool:
    if not user or not getattr(user, "pk", None):
        return False
    attr = _INAPP_ATTR.get(ntype)
    if not attr:
        return True
    try:
        prefs = getattr(user, "notification_prefs", None)
        if prefs is None:
            prefs = NotificationPreference.objects.filter(user_id=user.pk).first()
        if prefs is None:
            return _DEFAULT_INAPP.get(ntype, True)
        return bool(getattr(prefs, attr, True))
    except Exception:
        return _DEFAULT_INAPP.get(ntype, True)


def wants_email(user, ntype: str) -> bool:
    if not user or not getattr(user, "pk", None):
        return False
    if not getattr(user, "email", None):
        return False
    attr = _EMAIL_ATTR.get(ntype)
    if not attr:
        return False
    try:
        prefs = getattr(user, "notification_prefs", None)
        if prefs is None:
            prefs = NotificationPreference.objects.filter(user_id=user.pk).first()
        if prefs is None:
            return _DEFAULT_EMAIL.get(ntype, False)
        return bool(getattr(prefs, attr, False))
    except Exception:
        return _DEFAULT_EMAIL.get(ntype, False)
