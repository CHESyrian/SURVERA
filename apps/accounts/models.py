"""
Custom user model for SURVERA.
Email is the primary identifier.
"""
from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.translation import gettext_lazy as _


class User(AbstractUser):
    class UserType(models.TextChoices):
        PERSON = "person", _("Person")
        COMPANY_MEMBER = "company_member", _("Company Member")

    email = models.EmailField(_("email address"), unique=True)
    user_type = models.CharField(
        max_length=20,
        choices=UserType.choices,
        default=UserType.PERSON,
        db_index=True,
    )
    language = models.CharField(
        max_length=10,
        choices=[("en", "English"), ("ar", "العربية")],
        default="en",
    )
    is_email_verified = models.BooleanField(default=False)

    class Gender(models.TextChoices):
        UNSPECIFIED = "", _("Prefer not to say")
        FEMALE = "female", _("Female")
        MALE = "male", _("Male")
        OTHER = "other", _("Other")

    date_of_birth = models.DateField(_("date of birth"), null=True, blank=True)
    gender = models.CharField(
        _("gender"),
        max_length=20,
        choices=Gender.choices,
        blank=True,
        default="",
    )

    # Reputation ledger — separate from survey reward Points and XP.
    # UI label: "Reputation". Increased by daily/weekly tasks, quality, onboarding.
    honor_points = models.PositiveIntegerField(
        _("reputation"),
        default=0,
        db_index=True,
        help_text=_(
            "Reputation ledger (internal: honor_points). "
            "Raised by daily and weekly task completion, quality responses, and onboarding. "
            "Trust level is derived from this balance."
        ),
    )
    trust_level = models.PositiveSmallIntegerField(
        _("reputation level"),
        default=1,
        db_index=True,
        help_text=_(
            "1–7 Reputation level derived from honor_points "
            "(Newcomer … Distinguished). Used for survey targeting."
        ),
    )
    # Derived mirror of reputation level (0–100). Not used in product UI/targeting.
    trust_score = models.PositiveSmallIntegerField(
        _("reputation score (derived)"),
        default=15,
        help_text=_(
            "Optional 0–100 projection of reputation level. "
            "Source of truth is honor_points → trust_level. Not shown in UI."
        ),
    )

    # Moderation / penalties
    warning_count = models.PositiveSmallIntegerField(
        _("warning count"),
        default=0,
        help_text=_("Number of formal warnings received (progressive ladder)."),
    )
    frozen_until = models.DateTimeField(
        _("frozen until"),
        null=True,
        blank=True,
        help_text=_("If set and in the future, the account cannot sign in."),
    )
    closed_at = models.DateTimeField(
        _("permanently closed at"),
        null=True,
        blank=True,
        help_text=_("If set, the account is permanently closed."),
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    class Meta:
        verbose_name = _("user")
        verbose_name_plural = _("users")
        ordering = ["-date_joined"]

    def __str__(self) -> str:
        return self.email

    @property
    def is_person(self) -> bool:
        return self.user_type == self.UserType.PERSON

    @property
    def is_company_member(self) -> bool:
        return self.user_type == self.UserType.COMPANY_MEMBER

    @property
    def age(self) -> int | None:
        if not self.date_of_birth:
            return None
        from django.utils import timezone

        today = timezone.localdate()
        born = self.date_of_birth
        return today.year - born.year - (
            (today.month, today.day) < (born.month, born.day)
        )

    @property
    def trust_level_label(self) -> str:
        from apps.accounts.honor import band_for_level

        return band_for_level(self.trust_level or 1).name

    @property
    def is_permanently_closed(self) -> bool:
        return self.closed_at is not None

    @property
    def is_account_frozen(self) -> bool:
        if self.closed_at is not None:
            return True
        if not self.frozen_until:
            return False
        from django.utils import timezone

        return self.frozen_until > timezone.now()

    def moderation_block_reason(self) -> str | None:
        """Human-readable reason the account cannot authenticate, or None."""
        from django.utils import timezone
        from django.utils.translation import gettext as _

        if self.closed_at is not None:
            return str(_("This account has been permanently closed."))
        if self.frozen_until and self.frozen_until > timezone.now():
            return str(
                _("This account is frozen until %(when)s.")
                % {"when": self.frozen_until.strftime("%Y-%m-%d %H:%M UTC")}
            )
        return None


class HonorEvent(models.Model):
    """
    Ledger of honor point changes.

    Wired now: registration, email verification, basic profile.
    Reserved reasons support future quality scores, goals, medals, reports, penalties.
    """

    class Reason(models.TextChoices):
        REGISTRATION = "registration", _("Registration")
        EMAIL_VERIFIED = "email_verified", _("Email verified")
        PROFILE_BASIC = "profile_basic", _("Basic profile completed")
        SURVEY_QUALITY = "survey_quality", _("Survey response quality")
        DAILY_GOAL = "daily_goal", _("Daily goal")
        WEEKLY_GOAL = "weekly_goal", _("Weekly goal")
        ACHIEVEMENT = "achievement", _("Achievement / medal (reserved)")
        REPORT_PENALTY = "report_penalty", _("Report penalty")
        VIOLATION = "violation", _("Violation penalty")
        WARNING = "warning", _("Warning")
        ADMIN_ADJUST = "admin_adjust", _("Admin adjustment")
        SYSTEM = "system", _("System")

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="honor_events",
    )
    amount = models.IntegerField(help_text=_("Signed delta; negative for penalties."))
    balance_after = models.PositiveIntegerField()
    reason = models.CharField(max_length=40, choices=Reason.choices, db_index=True)
    note = models.CharField(max_length=300, blank=True)
    level_after = models.PositiveSmallIntegerField(default=1)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="honor_events_made",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("honor event")
        verbose_name_plural = _("honor events")
        indexes = [
            models.Index(fields=["user", "reason"]),
        ]

    def __str__(self) -> str:
        return f"Honor {self.user_id}: {self.amount:+d} → {self.balance_after} ({self.reason})"


class TrustEvent(models.Model):
    """
    Legacy/admin audit for direct trust_score edits.

    Prefer HonorEvent + apply_honor_delta for reputation changes.
    """

    class Reason(models.TextChoices):
        ADMIN_ADJUST = "admin_adjust", _("Admin adjustment")
        MANUAL = "manual", _("Manual")
        SYSTEM = "system", _("System")
        SURVEY_COMPLETION = "survey_completion", _("Survey completion (reserved)")
        FLAG = "flag", _("Flag / report (reserved)")

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="trust_events",
    )
    old_score = models.PositiveSmallIntegerField()
    new_score = models.PositiveSmallIntegerField()
    delta = models.IntegerField()
    reason = models.CharField(
        max_length=40,
        choices=Reason.choices,
        default=Reason.ADMIN_ADJUST,
        db_index=True,
    )
    note = models.CharField(max_length=300, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="trust_events_made",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("trust event")
        verbose_name_plural = _("trust events")

    def __str__(self) -> str:
        return f"Trust {self.user_id}: {self.old_score}→{self.new_score} ({self.reason})"
