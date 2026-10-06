"""Response (participation event) and Answer models."""
from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import TimeStampedModel


class Response(TimeStampedModel):
    class Status(models.TextChoices):
        IN_PROGRESS = "in_progress", _("In progress")
        COMPLETED = "completed", _("Completed")
        REJECTED = "rejected", _("Rejected")
        PARTIAL = "partial", _("Partial / abandoned")

    survey = models.ForeignKey(
        "surveys.Survey", on_delete=models.CASCADE, related_name="responses"
    )
    participant = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="survey_responses",
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.IN_PROGRESS, db_index=True
    )
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=400, blank=True)

    class Meta:
        verbose_name = _("response")
        verbose_name_plural = _("responses")
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["survey", "status"]),
            models.Index(fields=["participant", "survey"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["survey", "participant"],
                condition=models.Q(participant__isnull=False),
                name="unique_participant_per_survey",
            ),
        ]

    def __str__(self) -> str:
        who = self.participant.email if self.participant_id else "anonymous"
        return f"Response #{self.pk} – {self.survey_id} – {who} ({self.status})"


class Answer(TimeStampedModel):
    response = models.ForeignKey(Response, on_delete=models.CASCADE, related_name="answers")
    question = models.ForeignKey(
        "surveys.Question", on_delete=models.CASCADE, related_name="answers"
    )
    value = models.JSONField(_("value"))

    class Meta:
        verbose_name = _("answer")
        verbose_name_plural = _("answers")
        unique_together = [("response", "question")]
        ordering = ["question__order", "id"]

    def __str__(self) -> str:
        return f"Answer q={self.question_id} r={self.response_id}"



class QualityAssessment(TimeStampedModel):
    """Quality score for a completed survey response (v1 algorithm)."""

    class Tier(models.TextChoices):
        REJECT = "reject", _("Reject")
        LOW = "low", _("Low")
        STANDARD = "standard", _("Standard")
        HIGH = "high", _("High")

    response = models.OneToOneField(
        Response,
        on_delete=models.CASCADE,
        related_name="quality",
    )
    survey = models.ForeignKey(
        "surveys.Survey",
        on_delete=models.CASCADE,
        related_name="quality_assessments",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="quality_assessments",
    )
    score = models.FloatField(_("quality score"))
    tier = models.CharField(max_length=20, choices=Tier.choices, db_index=True)
    components = models.JSONField(default=dict, blank=True)
    flags = models.JSONField(default=list, blank=True)
    honor_granted = models.PositiveSmallIntegerField(default=0)
    expected_min_seconds = models.FloatField(null=True, blank=True)
    elapsed_seconds = models.FloatField(null=True, blank=True)

    class Meta:
        verbose_name = _("quality assessment")
        verbose_name_plural = _("quality assessments")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Quality r={self.response_id} {self.score} ({self.tier})"



class Report(TimeStampedModel):
    """
    Manager report against a participant response.

    Staff review in the admin control panel, then either:
    - apply a penalty (reputation and/or points) and notify both parties, or
    - dismiss with no penalty and notify the reporter only.
    """

    class Type(models.TextChoices):
        SPAM = "spam", _("Spam")
        LOW_QUALITY = "low_quality", _("Low quality")
        FRAUD = "fraud", _("Fraud / abuse")
        HARASSMENT = "harassment", _("Harassment")
        OTHER = "other", _("Other")

    class Status(models.TextChoices):
        PENDING = "pending", _("Pending")
        REVIEWING = "reviewing", _("Reviewing")
        RESOLVED = "resolved", _("Resolved")
        DISMISSED = "dismissed", _("Dismissed")

    class PenaltyKind(models.TextChoices):
        NONE = "none", _("None")
        WARNING = "warning", _("Warning (progressive ladder)")
        HONOR_DEDUCTION = "honor_deduction", _("Honor points deduction")
        RANK_REDUCTION = "rank_reduction", _("Rank reduction")
        ACCOUNT_FREEZE = "account_freeze", _("Account freeze")
        ACCOUNT_CLOSURE = "account_closure", _("Permanent account closure")
        # Legacy values kept for existing rows
        REPUTATION = "reputation", _("Reputation deduction (legacy)")
        POINTS = "points", _("Survey points deduction (legacy)")
        BOTH = "both", _("Reputation and points (legacy)")

    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="reports_filed",
    )
    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.CASCADE,
        related_name="reports",
    )
    survey = models.ForeignKey(
        "surveys.Survey",
        on_delete=models.CASCADE,
        related_name="reports",
    )
    response = models.ForeignKey(
        Response,
        on_delete=models.CASCADE,
        related_name="reports",
    )
    reported_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reports_received",
    )
    type = models.CharField(max_length=30, choices=Type.choices, db_index=True)
    note = models.TextField(_("note"))
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    resolution_note = models.TextField(
        _("resolution note"),
        blank=True,
        help_text=_("Shown to the reporter (and subject when a penalty is applied)."),
    )
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reports_resolved",
    )
    resolved_at = models.DateTimeField(null=True, blank=True)

    # Penalty (set when status becomes resolved with a penalty)
    penalty_kind = models.CharField(
        max_length=20,
        choices=PenaltyKind.choices,
        default=PenaltyKind.NONE,
        db_index=True,
    )
    penalty_reputation = models.PositiveIntegerField(
        _("honor points to deduct"),
        default=0,
        help_text=_(
            "Honor/Reputation points to deduct. "
            "For warnings, the ladder amount is applied automatically "
            "(1st=-100, 2nd=-200); this field stores what was applied."
        ),
    )
    penalty_points = models.PositiveIntegerField(
        _("survey points to deduct (legacy)"),
        default=0,
        help_text=_("Legacy survey Points deduction (optional)."),
    )
    penalty_rank_levels = models.PositiveSmallIntegerField(
        _("rank levels to drop"),
        default=1,
        help_text=_("How many trust ranks to drop (rank reduction penalty)."),
    )
    penalty_freeze_days = models.PositiveIntegerField(
        _("freeze duration (days)"),
        default=0,
        help_text=_("Account freeze length in days (account_freeze penalty)."),
    )
    penalty_executed_at = models.DateTimeField(
        _("penalty executed at"),
        null=True,
        blank=True,
    )
    # Snapshot of progressive warning after execution
    warning_number = models.PositiveSmallIntegerField(
        _("warning number applied"),
        null=True,
        blank=True,
        help_text=_("Which warning in the ladder this was (1–5+), if kind=warning."),
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("report")
        verbose_name_plural = _("reports")
        indexes = [
            models.Index(fields=["status", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"Report #{self.pk} {self.type} ({self.status})"

    @property
    def is_open(self) -> bool:
        return self.status in {self.Status.PENDING, self.Status.REVIEWING}

    @property
    def has_penalty(self) -> bool:
        return self.penalty_kind not in {self.PenaltyKind.NONE, ""}
