"""Application services for company creation and membership."""
from __future__ import annotations

import logging

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils.translation import gettext_lazy as _

from apps.common.constants import PLATFORM_COMPANY_NAME, PLATFORM_COMPANY_SLUG

from .models import Company, CompanyMembership

User = get_user_model()
logger = logging.getLogger(__name__)

# Product-facing roles only (invite / role-change UI).
ASSIGNABLE_ROLES = [
    CompanyMembership.Role.MODERATOR,
    CompanyMembership.Role.PARTICIPANT,
]

# All product role values (for validation / docs).
PRODUCT_ROLES = frozenset(
    {
        CompanyMembership.Role.OWNER,
        CompanyMembership.Role.MODERATOR,
        CompanyMembership.Role.PARTICIPANT,
    }
)


def get_platform_company() -> Company | None:
    return Company.objects.filter(slug=PLATFORM_COMPANY_SLUG).first()


@transaction.atomic
def get_or_create_platform_company() -> Company:
    """Ensure the SURVERA platform company exists (idempotent)."""
    company = Company.objects.filter(slug=PLATFORM_COMPANY_SLUG).first()
    if company:
        if company.name != PLATFORM_COMPANY_NAME:
            company.name = PLATFORM_COMPANY_NAME
            company.save(update_fields=["name", "updated_at"])
        return company
    company = Company(name=PLATFORM_COMPANY_NAME, slug=PLATFORM_COMPANY_SLUG)
    company.save()
    return company


@transaction.atomic
def ensure_superuser_on_platform(user) -> CompanyMembership | None:
    """
    Add superuser as moderator on SURVERA company (idempotent).

    Superusers already bypass company checks in views; membership keeps
    Discover/team UI consistent. Legacy `admin` rows are left as-is (still manage).
    """
    if not user or not getattr(user, "is_superuser", False):
        return None
    company = get_or_create_platform_company()
    membership = CompanyMembership.objects.filter(company=company, user=user).first()
    manage_roles = {
        CompanyMembership.Role.OWNER,
        CompanyMembership.Role.MODERATOR,
        CompanyMembership.Role.ADMIN,
    }
    if membership:
        changed = False
        if not membership.is_active:
            membership.is_active = True
            changed = True
        if membership.role not in manage_roles:
            membership.role = CompanyMembership.Role.MODERATOR
            changed = True
        if changed:
            membership.save(update_fields=["is_active", "role", "updated_at"])
        return membership
    return CompanyMembership.objects.create(
        company=company,
        user=user,
        role=CompanyMembership.Role.MODERATOR,
        is_active=True,
    )


@transaction.atomic
def ensure_all_superusers_on_platform() -> int:
    """Attach every superuser to SURVERA as moderator. Returns changed count."""
    n = 0
    for user in User.objects.filter(is_superuser=True, is_active=True):
        before = CompanyMembership.objects.filter(
            company__slug=PLATFORM_COMPANY_SLUG, user=user
        ).first()
        ensure_superuser_on_platform(user)
        after = CompanyMembership.objects.filter(
            company__slug=PLATFORM_COMPANY_SLUG, user=user
        ).first()
        if after and (before is None or before.role != after.role or not before.is_active):
            n += 1
        elif before is None and after:
            n += 1
    return n


@transaction.atomic
def create_company_with_owner(*, owner, name: str, promote_user_type: bool = True) -> Company:
    company = Company.objects.create(name=name.strip())
    CompanyMembership.objects.create(
        company=company,
        user=owner,
        role=CompanyMembership.Role.OWNER,
        is_active=True,
    )
    if promote_user_type and owner.user_type != owner.UserType.COMPANY_MEMBER:
        owner.user_type = owner.UserType.COMPANY_MEMBER
        owner.save(update_fields=["user_type"])
    return company


def normalize_assignable_role(role: str) -> str:
    """Map legacy admin → moderator; reject non-product assignable roles."""
    if role == CompanyMembership.Role.ADMIN:
        return CompanyMembership.Role.MODERATOR
    if role == CompanyMembership.Role.OWNER:
        raise ValueError(_("Cannot assign owner via invite."))
    allowed = {str(r) for r in ASSIGNABLE_ROLES}
    if role not in allowed:
        raise ValueError(_("Invalid role."))
    return role


def roles_assignable_by(user, company) -> list[str]:
    """Roles the given user may assign on this company."""
    m = get_active_membership(user, company)
    if not m:
        return []
    return m.roles_assignable_by_self()


@transaction.atomic
def add_company_member(
    *, company, email: str, role: str, invited_by
) -> CompanyMembership:
    email = email.lower().strip()
    if not email:
        raise ValueError(_("Email is required."))

    try:
        user = User.objects.get(email__iexact=email)
    except User.DoesNotExist as exc:
        raise ValueError(_("No user with that email. They must register first.")) from exc

    role = normalize_assignable_role(role)

    inviter_membership = get_active_membership(invited_by, company)
    if inviter_membership is None and not getattr(invited_by, "is_superuser", False):
        raise ValueError(_("You cannot manage this team."))
    if inviter_membership is not None:
        allowed_by_inviter = set(inviter_membership.roles_assignable_by_self())
        if role not in allowed_by_inviter and not getattr(invited_by, "is_superuser", False):
            raise ValueError(_("You cannot assign that role."))

    existing = CompanyMembership.objects.filter(company=company, user=user).first()
    if existing:
        if existing.is_active:
            raise ValueError(_("This user is already a member of the company."))
        existing.role = role
        existing.is_active = True
        existing.save(update_fields=["role", "is_active", "updated_at"])
        _notify_team_invite(
            user=user, company=company, role=role, invited_by=invited_by, reactivated=True
        )
        return existing

    membership = CompanyMembership.objects.create(
        company=company,
        user=user,
        role=role,
        is_active=True,
    )
    _notify_team_invite(
        user=user, company=company, role=role, invited_by=invited_by, reactivated=False
    )
    return membership


@transaction.atomic
def change_member_role(
    *, company, membership: CompanyMembership, new_role: str, changed_by
) -> CompanyMembership:
    """Change a non-owner member's role within the changer's assignment rights."""
    if membership.company_id != company.pk:
        raise ValueError(_("Membership does not belong to this company."))
    if membership.role == CompanyMembership.Role.OWNER:
        raise ValueError(_("Cannot change the owner role here."))

    new_role = normalize_assignable_role(new_role)

    changer = get_active_membership(changed_by, company)
    if changer is None and not getattr(changed_by, "is_superuser", False):
        raise ValueError(_("You cannot manage this team."))
    if changer is not None:
        allowed = set(changer.roles_assignable_by_self())
        if new_role not in allowed and not getattr(changed_by, "is_superuser", False):
            raise ValueError(_("You cannot assign that role."))

    membership.role = new_role
    membership.save(update_fields=["role", "updated_at"])
    return membership


def _notify_team_invite(*, user, company, role, invited_by, reactivated: bool) -> None:
    try:
        from apps.notifications.services import notify_team_invite

        notify_team_invite(
            user=user,
            company=company,
            role=role,
            invited_by=invited_by,
            reactivated=reactivated,
        )
    except Exception:
        logger.exception(
            "Team invite notification failed (company_id=%s user_id=%s role=%s reactivated=%s)",
            company.pk,
            user.pk,
            role,
            reactivated,
        )


def get_active_membership(user, company) -> CompanyMembership | None:
    if not user or not user.is_authenticated or company is None:
        return None
    return CompanyMembership.objects.filter(
        company=company, user=user, is_active=True
    ).first()


def user_can_manage_team(user, company) -> bool:
    m = get_active_membership(user, company)
    return bool(m and m.can_manage_team)


def user_can_manage_surveys(user, company) -> bool:
    m = get_active_membership(user, company)
    return bool(m and m.can_manage_surveys)


def user_is_company_member(user, company) -> bool:
    return get_active_membership(user, company) is not None
