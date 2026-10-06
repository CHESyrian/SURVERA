"""Company and membership models for SURVERA multi-tenancy."""
from django.conf import settings
from django.db import models
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from apps.common.models import SoftDeleteModel, TimeStampedModel


class Company(TimeStampedModel, SoftDeleteModel):
    class Status(models.TextChoices):
        ACTIVE = "active", _("Active")
        SUSPENDED = "suspended", _("Suspended")
        PENDING = "pending", _("Pending")

    name = models.CharField(_("name"), max_length=200)
    slug = models.SlugField(_("slug"), max_length=220, unique=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
        db_index=True,
    )
    logo = models.ImageField(_("logo"), upload_to="companies/logos/", blank=True, null=True)
    primary_color = models.CharField(max_length=7, blank=True, default="#2563eb")

    class Meta:
        verbose_name = _("company")
        verbose_name_plural = _("companies")
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name) or "company"
            slug = base
            counter = 1
            while Company.all_objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)


class CompanyMembership(TimeStampedModel):
    """
    Product roles (canonical):
      - owner: full company control (settings, team, surveys)
      - moderator: surveys + invite participants (not full company control)
      - participant: take surveys only

    Legacy role values remain in the DB/choices for migration compatibility
    and are mapped in permission helpers only. They are not offered in invite UI.
    """

    class Role(models.TextChoices):
        OWNER = "owner", _("Owner")
        MODERATOR = "moderator", _("Moderator")
        PARTICIPANT = "participant", _("Participant")
        # Legacy (kept for existing rows; not assignable in product UI)
        ADMIN = "admin", _("Admin (legacy)")
        RESEARCHER = "researcher", _("Researcher (legacy)")
        ANALYST = "analyst", _("Analyst (legacy)")
        VIEWER = "viewer", _("Viewer (legacy)")

    # Roles that manage surveys / results / CSV
    _MANAGE_SURVEY_ROLES = frozenset(
        {
            Role.OWNER,
            Role.MODERATOR,
            Role.ADMIN,  # legacy → treated as moderator
        }
    )
    # Roles that can manage team membership
    _MANAGE_TEAM_ROLES = frozenset(
        {
            Role.OWNER,
            Role.MODERATOR,
            Role.ADMIN,  # legacy → treated as moderator
        }
    )

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="company_memberships",
    )
    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.PARTICIPANT,
        db_index=True,
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = _("company membership")
        verbose_name_plural = _("company memberships")
        unique_together = [("company", "user")]
        ordering = ["company", "role"]

    def __str__(self) -> str:
        return f"{self.user.email} @ {self.company.name} ({self.role})"

    @property
    def is_owner(self) -> bool:
        return self.role == self.Role.OWNER

    @property
    def is_admin_or_owner(self) -> bool:
        """Owner, moderator, or legacy admin — full management tier."""
        return self.role in self._MANAGE_SURVEY_ROLES

    @property
    def can_manage_surveys(self) -> bool:
        """Create / edit / publish surveys and view results / CSV."""
        return self.role in self._MANAGE_SURVEY_ROLES

    @property
    def can_manage_team(self) -> bool:
        """Invite / remove members (assignment scope differs by role — see services)."""
        return self.role in self._MANAGE_TEAM_ROLES

    def roles_assignable_by_self(self) -> list[str]:
        """
        Roles this membership may assign when inviting or changing roles.

        - Owner: moderator + participant
        - Moderator (and legacy admin): participant only
        - Others: none
        """
        if not self.is_active:
            return []
        if self.role == self.Role.OWNER:
            return [self.Role.MODERATOR, self.Role.PARTICIPANT]
        if self.role in {self.Role.MODERATOR, self.Role.ADMIN}:
            return [self.Role.PARTICIPANT]
        return []
