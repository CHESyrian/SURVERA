"""Rewards domain: Points (redeemable) and XP / levels / badges."""
from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import TimeStampedModel


class PointsTransaction(TimeStampedModel):
    class Reason(models.TextChoices):
        SURVEY_COMPLETION = "survey_completion", _("Survey completion")
        ADJUSTMENT = "adjustment", _("Manual adjustment")

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="points_transactions"
    )
    amount = models.IntegerField(_("amount"))
    reason = models.CharField(max_length=40, choices=Reason.choices)
    response = models.ForeignKey(
        "responses.Response",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="points_transactions",
    )
    note = models.CharField(max_length=255, blank=True)
    balance_after = models.IntegerField(_("balance after"), default=0)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "-created_at"])]


class XPTransaction(TimeStampedModel):
    class Reason(models.TextChoices):
        SURVEY_COMPLETION = "survey_completion", _("Survey completion")
        PROFILE_COMPLETE = "profile_complete", _("Profile completed")
        DAILY_LOGIN = "daily_login", _("Daily login")
        SURVEY_CREATED = "survey_created", _("Survey created")
        BADGE_BONUS = "badge_bonus", _("Badge bonus")
        TASK_DAILY = "task_daily", _("Daily task")
        TASK_WEEKLY = "task_weekly", _("Weekly task")
        ADJUSTMENT = "adjustment", _("Manual adjustment")

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="xp_transactions"
    )
    amount = models.PositiveIntegerField(_("amount"))
    reason = models.CharField(max_length=40, choices=Reason.choices)
    response = models.ForeignKey(
        "responses.Response",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="xp_transactions",
    )
    note = models.CharField(max_length=255, blank=True)
    total_after = models.PositiveIntegerField(_("total XP after"), default=0)
    level_after = models.PositiveIntegerField(_("level after"), default=1)

    class Meta:
        ordering = ["-created_at"]


class UserProgress(TimeStampedModel):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="progress"
    )
    xp_total = models.PositiveIntegerField(default=0)
    level = models.PositiveIntegerField(default=1)
    surveys_completed = models.PositiveIntegerField(default=0)
    surveys_created = models.PositiveIntegerField(default=0)
    last_login_xp_date = models.DateField(null=True, blank=True)

    def __str__(self) -> str:
        return f"{self.user_id} L{self.level} ({self.xp_total} XP)"


class Badge(TimeStampedModel):
    code = models.SlugField(unique=True)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=50, blank=True)
    xp_bonus = models.PositiveIntegerField(default=0)
    criteria = models.JSONField(default=dict, blank=True)

    def __str__(self) -> str:
        return self.name


class UserBadge(TimeStampedModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="badges"
    )
    badge = models.ForeignKey(Badge, on_delete=models.CASCADE, related_name="holders")

    class Meta:
        unique_together = [("user", "badge")]



class TaskDefinition(TimeStampedModel):
    """Catalog of daily / weekly / general tasks."""

    class Kind(models.TextChoices):
        DAILY = "daily", _("Daily")
        WEEKLY = "weekly", _("Weekly")
        GENERAL = "general", _("General")

    class Metric(models.TextChoices):
        SURVEYS_COMPLETED = "surveys_completed", _("Surveys completed")

    code = models.SlugField(unique=True, max_length=64)
    kind = models.CharField(max_length=20, choices=Kind.choices, db_index=True)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    metric = models.CharField(
        max_length=40, choices=Metric.choices, default=Metric.SURVEYS_COMPLETED
    )
    target_count = models.PositiveIntegerField(default=1)
    honor_reward = models.PositiveIntegerField(default=0)
    xp_reward = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True, db_index=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["kind", "sort_order", "id"]
        verbose_name = _("task definition")
        verbose_name_plural = _("task definitions")

    def __str__(self) -> str:
        return f"{self.code} ({self.kind})"


class TaskProgress(TimeStampedModel):
    """Per-user progress for a task in a period (day / week / once)."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="task_progress",
    )
    definition = models.ForeignKey(
        TaskDefinition,
        on_delete=models.CASCADE,
        related_name="progress_rows",
    )
    period_key = models.CharField(
        max_length=16,
        db_index=True,
        help_text=_("YYYY-MM-DD for daily, YYYY-Www for weekly, empty for general."),
    )
    current_count = models.PositiveIntegerField(default=0)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-updated_at"]
        verbose_name = _("task progress")
        verbose_name_plural = _("task progress")
        constraints = [
            models.UniqueConstraint(
                fields=["user", "definition", "period_key"],
                name="unique_task_progress_period",
            )
        ]

    def __str__(self) -> str:
        return f"{self.user_id}:{self.definition_id}:{self.period_key} ({self.current_count})"

    @property
    def is_complete(self) -> bool:
        return self.completed_at is not None
