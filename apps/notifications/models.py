"""In-app notifications for SURVERA users."""
from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.common.models import TimeStampedModel


class Notification(TimeStampedModel):
    class Type(models.TextChoices):
        SURVEY_PUBLISHED = "survey_published", _("Survey published")
        POINTS_AWARDED = "points_awarded", _("Coins awarded")
        TEAM_INVITE = "team_invite", _("Team invite")
        SYSTEM = "system", _("System")

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    type = models.CharField(max_length=40, choices=Type.choices, db_index=True)
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True)
    link = models.CharField(
        max_length=500,
        blank=True,
        help_text=_("Relative URL path, e.g. /r/take/12/"),
    )
    payload = models.JSONField(default=dict, blank=True)
    read_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "read_at", "-created_at"]),
            models.Index(fields=["user", "-created_at"]),
        ]
        verbose_name = _("notification")
        verbose_name_plural = _("notifications")

    def __str__(self) -> str:
        return f"{self.user_id}: {self.title}"

    @property
    def is_read(self) -> bool:
        return self.read_at is not None

    def mark_read(self) -> None:
        if self.read_at is None:
            self.read_at = timezone.now()
            self.save(update_fields=["read_at", "updated_at"])
