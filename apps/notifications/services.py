"""Notification creation and fan-out helpers."""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import QuerySet
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.companies.models import CompanyMembership

from .models import Notification

User = get_user_model()

# Safety cap for bulk publish fan-out (sync path).
MAX_PUBLISH_RECIPIENTS = 500


def unread_count(user) -> int:
    if not user or not getattr(user, "is_authenticated", False):
        return 0
    return Notification.objects.filter(user=user, read_at__isnull=True).count()


def user_notifications(user, *, limit: int = 50) -> QuerySet[Notification]:
    return Notification.objects.filter(user=user).order_by("-created_at")[:limit]


@transaction.atomic
def notify_user(
    *,
    user,
    type: str,
    title: str,
    body: str = "",
    link: str = "",
    payload: dict | None = None,
) -> Notification | None:
    if not user or not getattr(user, "is_active", True):
        return None
    from .preferences import wants_inapp

    if not wants_inapp(user, type):
        return None
    return Notification.objects.create(
        user=user,
        type=type,
        title=title[:200],
        body=body or "",
        link=link or "",
        payload=payload or {},
    )


@transaction.atomic
def notify_users(
    *,
    users,
    type: str,
    title: str,
    body: str = "",
    link: str = "",
    payload: dict | None = None,
) -> int:
    """Bulk-create the same notification for many users. Returns count created."""
    from .preferences import wants_inapp

    payload = payload or {}
    objs = []
    seen: set[int] = set()
    for user in users:
        if not user or not getattr(user, "pk", None):
            continue
        if user.pk in seen:
            continue
        if not getattr(user, "is_active", True):
            continue
        if not wants_inapp(user, type):
            continue
        seen.add(user.pk)
        objs.append(
            Notification(
                user=user,
                type=type,
                title=title[:200],
                body=body or "",
                link=link or "",
                payload=payload,
            )
        )
    if not objs:
        return 0
    Notification.objects.bulk_create(objs, batch_size=200)
    return len(objs)


def mark_read(notification: Notification, user) -> Notification:
    if notification.user_id != user.pk:
        raise PermissionError("Not your notification.")
    notification.mark_read()
    return notification


@transaction.atomic
def mark_all_read(user) -> int:
    now = timezone.now()
    return Notification.objects.filter(user=user, read_at__isnull=True).update(
        read_at=now, updated_at=now
    )


def _eligible_members_for_survey(survey) -> list:
    """Active company members who can access the survey (targeting + private)."""
    if not survey.company_id:
        return []

    from apps.surveys.targeting import can_access_survey

    memberships = (
        CompanyMembership.objects.filter(company_id=survey.company_id, is_active=True)
        .select_related("user")
        .order_by("id")[: MAX_PUBLISH_RECIPIENTS + 50]
    )
    recipients = []
    exclude_id = survey.created_by_id
    for m in memberships:
        user = m.user
        if not user or not user.is_active:
            continue
        if exclude_id and user.pk == exclude_id:
            continue
        ok, _ = can_access_survey(user, survey)
        if ok:
            recipients.append(user)
        if len(recipients) >= MAX_PUBLISH_RECIPIENTS:
            break
    return recipients


@transaction.atomic
def notify_survey_published(survey) -> int:
    """
    Notify eligible participants when a survey becomes active.

    - members_only / private: company members who pass targeting
    - public (no members_only): company members only (not the whole platform)
    """
    from apps.surveys.models import Survey

    if survey.status != Survey.Status.ACTIVE:
        return 0
    if not survey.company_id:
        return 0

    recipients = _eligible_members_for_survey(survey)
    if not recipients:
        return 0

    company_name = ""
    try:
        company_name = survey.company.name
    except Exception:
        company_name = str(_("Company"))

    points_note = ""
    if survey.is_paid and survey.points_reward:
        points_note = " " + str(
            _("Reward: %(n)s points.") % {"n": survey.points_reward}
        )

    title = str(_("New survey: %(title)s") % {"title": survey.title[:120]})
    body = str(
        _("%(company)s published a survey you can take.%(points)s")
        % {"company": company_name, "points": points_note}
    )
    try:
        link = reverse("responses:take", kwargs={"pk": survey.pk})
    except Exception:
        link = f"/r/take/{survey.pk}/"

    return notify_users(
        users=recipients,
        type=Notification.Type.SURVEY_PUBLISHED,
        title=title,
        body=body,
        link=link,
        payload={
            "survey_id": survey.pk,
            "company_id": survey.company_id,
            "is_paid": survey.is_paid,
            "points_reward": survey.points_reward or 0,
        },
    )


@transaction.atomic
def notify_points_awarded(*, user, amount: int, survey_title: str = "", response_id=None) -> Notification | None:
    if amount <= 0 or not user:
        return None
    title = str(_("You earned %(n)s points") % {"n": amount})
    body = ""
    if survey_title:
        body = str(_("For completing “%(t)s”.") % {"t": survey_title[:120]})
    return notify_user(
        user=user,
        type=Notification.Type.POINTS_AWARDED,
        title=title,
        body=body,
        link=reverse("accounts:profile") if user else "",
        payload={"amount": amount, "response_id": response_id},
    )


@transaction.atomic
def notify_team_invite(
    *,
    user,
    company,
    role: str,
    invited_by=None,
    reactivated: bool = False,
) -> Notification | None:
    """Notify a user they were added (or re-invited) to a company team."""
    if not user or not company:
        return None

    company_name = getattr(company, "name", "") or str(_("Company"))
    role_label = role
    try:
        role_label = str(CompanyMembership.Role(role).label)
    except Exception:
        role_label = str(role).replace("_", " ").title()

    if reactivated:
        title = str(_("You're back on %(company)s") % {"company": company_name[:100]})
        body = str(
            _("Your membership was reactivated as %(role)s.") % {"role": role_label}
        )
    else:
        title = str(_("Joined %(company)s") % {"company": company_name[:100]})
        body = str(
            _("You were added to the team as %(role)s.") % {"role": role_label}
        )

    if invited_by is not None:
        inviter = (
            getattr(invited_by, "username", None)
            or getattr(invited_by, "email", None)
            or ""
        )
        if inviter:
            body = f"{body} " + str(_("Invited by %(who)s.") % {"who": inviter})

    try:
        link = reverse("companies:team", kwargs={"pk": company.pk})
    except Exception:
        link = f"/companies/{company.pk}/team/"

    note = notify_user(
        user=user,
        type=Notification.Type.TEAM_INVITE,
        title=title,
        body=body,
        link=link,
        payload={
            "company_id": company.pk,
            "company_name": company_name,
            "role": role,
            "invited_by_id": getattr(invited_by, "pk", None),
            "reactivated": reactivated,
        },
    )
    from .preferences import wants_email

    if wants_email(user, Notification.Type.TEAM_INVITE):
        _queue_team_invite_email(
            user=user,
            company=company,
            role_label=role_label,
            body=body,
            link=link,
            reactivated=reactivated,
        )
    return note


def _queue_team_invite_email(*, user, company, role_label, body, link, reactivated) -> None:
    """Queue (or run eagerly) team-invite email — never raise."""
    try:
        from .tasks import task_send_team_invite_email

        task_send_team_invite_email.delay(
            user_id=user.pk,
            company_id=company.pk,
            role_label=str(role_label),
            body=body,
            link=link,
            reactivated=reactivated,
        )
    except Exception:
        # Fallback: send inline if broker unavailable
        try:
            from .email import email_team_invite

            email_team_invite(
                user=user,
                company=company,
                role_label=str(role_label),
                body=body,
                link=link,
                reactivated=reactivated,
            )
        except Exception:
            pass


def queue_survey_published_notifications(survey) -> None:
    """
    Enqueue async fan-out for a published survey.

    Prefer Celery; fall back to sync notify if the broker is down.
    """
    survey_id = getattr(survey, "pk", None)
    if not survey_id:
        return
    try:
        from .tasks import task_notify_survey_published

        task_notify_survey_published.delay(survey_id)
    except Exception:
        try:
            notify_survey_published(survey)
        except Exception:
            pass
