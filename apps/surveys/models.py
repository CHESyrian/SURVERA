"""Survey aggregate and Question models for SURVERA."""
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import SoftDeleteModel, TimeStampedModel, UserOwnedModel


class Survey(TimeStampedModel, SoftDeleteModel, UserOwnedModel):
    """
    Company-owned survey only.

    - company: owning organization (required; platform surveys use SURVERA company)
    - created_by: user who created the row (from UserOwnedModel; audit only)
    Permissions use company membership, not created_by.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", _("Draft")
        ACTIVE = "active", _("Active")
        PAUSED = "paused", _("Paused")
        CLOSED = "closed", _("Closed")

    class Visibility(models.TextChoices):
        PRIVATE = "private", _("Private (invite / targeted only)")
        PUBLIC = "public", _("Public (discoverable)")

    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.CASCADE,
        related_name="surveys",
        help_text=_("Owning company (including platform company SURVERA)."),
    )
    title = models.CharField(_("title"), max_length=300)
    description = models.TextField(_("description"), blank=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True
    )
    visibility = models.CharField(
        max_length=20, choices=Visibility.choices, default=Visibility.PUBLIC
    )
    is_paid = models.BooleanField(
        _("paid survey"),
        default=False,
        db_index=True,
        help_text=_("Paid surveys may grant points. Free surveys grant XP only."),
    )
    points_reward = models.PositiveIntegerField(
        _("points reward"),
        default=0,
        help_text=_("Coins given to participant on successful completion (paid surveys only)."),
    )
    response_target = models.PositiveIntegerField(
        _("response target"), null=True, blank=True
    )
    allow_anonymous = models.BooleanField(_("allow anonymous"), default=True)
    is_frozen = models.BooleanField(_("is frozen"), default=False, db_index=True)
    frozen_at = models.DateTimeField(_("frozen at"), null=True, blank=True)
    expires_at = models.DateTimeField(_("expires at"), null=True, blank=True, db_index=True)
    targeting = models.JSONField(_("targeting"), default=dict, blank=True)
    category = models.CharField(_("category"), max_length=100, blank=True, db_index=True)
    tags = models.JSONField(_("tags"), default=list, blank=True)

    class Meta:
        verbose_name = _("survey")
        verbose_name_plural = _("surveys")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "visibility"]),
            models.Index(fields=["company", "status"]),
        ]

    def __str__(self) -> str:
        return self.title

    def clean(self):
        if not self.company_id:
            raise ValidationError({"company": _("Survey must belong to a company.")})
        if not self.is_paid:
            self.points_reward = 0
            self.response_target = None
            self.visibility = self.Visibility.PUBLIC

    @property
    def is_platform(self) -> bool:
        """True when owned by the SURVERA platform company (slug=survera)."""
        if not self.company_id:
            return False
        # Prefer already-loaded relation; avoid raising on broken FK.
        company = getattr(self, "company", None)
        if company is not None:
            return company.slug == "survera"
        return False

    @property
    def owner_label(self) -> str:
        company = getattr(self, "company", None)
        if company is not None:
            return company.name
        return str(_("Company"))

    @property
    def is_editable(self) -> bool:
        return not self.is_frozen and self.status == self.Status.DRAFT

    def can_accept_responses(self) -> bool:
        if self.status != self.Status.ACTIVE or self.is_deleted:
            return False
        if self.expires_at:
            from django.utils import timezone

            if timezone.now() >= self.expires_at:
                return False
        return True


class Question(TimeStampedModel):
    class Type(models.TextChoices):
        TEXT = "text", _("Text (short / long)")
        SINGLE_CHOICE = "single_choice", _("Single choice")
        MULTIPLE_CHOICE = "multiple_choice", _("Multiple choice")
        YES_NO = "yes_no", _("Yes / No")
        RATING = "rating", _("Rating (stars / numbers)")
        SCALE = "scale", _("Scale (e.g. 1–10)")
        NUMBER = "number", _("Number")
        DATE = "date", _("Date")
        RANKING = "ranking", _("Ranking")
        MATRIX = "matrix", _("Matrix")

    survey = models.ForeignKey(Survey, on_delete=models.CASCADE, related_name="questions")
    order = models.PositiveIntegerField(_("order"), default=0, db_index=True)
    type = models.CharField(max_length=30, choices=Type.choices, default=Type.TEXT)
    text = models.TextField(_("question text"))
    help_text = models.CharField(_("help text"), max_length=500, blank=True)
    is_required = models.BooleanField(_("required"), default=True)
    config = models.JSONField(_("config"), default=dict, blank=True)
    conditions = models.JSONField(_("conditions"), default=list, blank=True)

    class Meta:
        verbose_name = _("question")
        verbose_name_plural = _("questions")
        ordering = ["survey", "order", "id"]
        indexes = [models.Index(fields=["survey", "order"])]

    def __str__(self) -> str:
        return f"{self.order}. {self.text[:60]}"

    def clean(self):
        cfg = self.config or {}
        if self.type in {self.Type.SINGLE_CHOICE, self.Type.MULTIPLE_CHOICE}:
            choices = cfg.get("choices")
            if not choices or not isinstance(choices, list) or len(choices) < 2:
                raise ValidationError(
                    _("Choice questions need a 'choices' list with at least 2 options.")
                )
        elif self.type == self.Type.RANKING:
            items = cfg.get("items")
            if not items or not isinstance(items, list) or len(items) < 2:
                raise ValidationError(_("Ranking questions need at least 2 items."))
        elif self.type == self.Type.MATRIX:
            rows = cfg.get("rows") or []
            cols = cfg.get("columns") or []
            if len(rows) < 1 or len(cols) < 2:
                raise ValidationError(_("Matrix questions need rows and at least 2 columns."))
        elif self.type == self.Type.RATING:
            max_val = cfg.get("max", 5)
            if not isinstance(max_val, int) or max_val < 2 or max_val > 10:
                raise ValidationError(_("Rating 'max' must be an integer between 2 and 10."))
        elif self.type == self.Type.SCALE:
            min_val = cfg.get("min", 1)
            max_val = cfg.get("max", 10)
            if not isinstance(min_val, int) or not isinstance(max_val, int) or min_val >= max_val:
                raise ValidationError(_("Scale needs integer min < max."))
