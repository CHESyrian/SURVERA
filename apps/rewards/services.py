"""Points and XP awarding services."""
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.accounts.decorators import user_email_verified

from .levels import (
    XP_DAILY_LOGIN,
    XP_PROFILE_COMPLETE,
    XP_SURVEY_COMPLETION,
    XP_SURVEY_CREATED,
    level_for_xp,
)
from .models import Badge, PointsTransaction, UserBadge, UserProgress, XPTransaction


def get_points_balance(user) -> int:
    total = PointsTransaction.objects.filter(user=user).aggregate(s=Sum("amount"))["s"] or 0
    return int(total)


def get_or_create_progress(user) -> UserProgress:
    progress, _ = UserProgress.objects.get_or_create(user=user)
    return progress


def get_xp_total(user) -> int:
    progress = getattr(user, "progress", None)
    if progress is not None:
        return progress.xp_total
    p = UserProgress.objects.filter(user=user).first()
    return p.xp_total if p else 0


def _badge_criteria_met(*, user, progress, criteria: dict) -> bool:
    """Return True when all known criteria keys are satisfied (unknown keys ignored)."""
    if not criteria:
        return False
    if "min_level" in criteria and progress.level < int(criteria["min_level"]):
        return False
    if "min_surveys_completed" in criteria and progress.surveys_completed < int(
        criteria["min_surveys_completed"]
    ):
        return False
    if "min_surveys_created" in criteria and progress.surveys_created < int(
        criteria["min_surveys_created"]
    ):
        return False
    if "min_honor" in criteria and int(getattr(user, "honor_points", 0) or 0) < int(
        criteria["min_honor"]
    ):
        return False
    return True


def _badge_progress(*, user, progress, criteria: dict) -> tuple[int, int]:
    """
    Best-effort (current, target) for the primary criterion — used in locked UI.
    Prefers surveys_completed, then level, then honor, then surveys_created.
    """
    if not criteria:
        return (0, 1)
    if "min_surveys_completed" in criteria:
        target = max(1, int(criteria["min_surveys_completed"]))
        return (min(progress.surveys_completed, target), target)
    if "min_level" in criteria:
        target = max(1, int(criteria["min_level"]))
        return (min(progress.level, target), target)
    if "min_honor" in criteria:
        target = max(1, int(criteria["min_honor"]))
        current = int(getattr(user, "honor_points", 0) or 0)
        return (min(current, target), target)
    if "min_surveys_created" in criteria:
        target = max(1, int(criteria["min_surveys_created"]))
        return (min(progress.surveys_created, target), target)
    return (0, 1)


def evaluate_badges(user) -> list:
    """
    Award any newly earned badges. Returns list of newly created UserBadge rows.
    """
    if not user_email_verified(user):
        return []
    progress = get_or_create_progress(user)
    newly: list = []
    for badge in Badge.objects.all():
        if UserBadge.objects.filter(user=user, badge=badge).exists():
            continue
        crit = badge.criteria or {}
        if not _badge_criteria_met(user=user, progress=progress, criteria=crit):
            continue
        ub = UserBadge.objects.create(user=user, badge=badge)
        newly.append(ub)
        if badge.xp_bonus:
            award_xp(user=user, amount=badge.xp_bonus, reason=XPTransaction.Reason.BADGE_BONUS)
    return newly


def list_profile_badges(user) -> list[dict]:
    """
    Full badge catalog for profile UI: earned + locked with progress.
    Each item:
      badge, earned (bool), user_badge|None, current, target, percent
    """
    progress = get_or_create_progress(user)
    earned_map = {
        ub.badge_id: ub
        for ub in UserBadge.objects.filter(user=user).select_related("badge")
    }
    items: list[dict] = []
    for badge in Badge.objects.order_by("id"):
        ub = earned_map.get(badge.pk)
        crit = badge.criteria or {}
        current, target = _badge_progress(user=user, progress=progress, criteria=crit)
        percent = min(100, int(100 * current / max(1, target)))
        if ub is not None:
            percent = 100
            current = target
        items.append(
            {
                "badge": badge,
                "earned": ub is not None,
                "user_badge": ub,
                "current": current,
                "target": target,
                "percent": percent,
            }
        )
    # Earned first (newest), then locked by id
    items.sort(key=lambda x: (0 if x["earned"] else 1, -(x["user_badge"].pk if x["user_badge"] else 0), x["badge"].pk))
    return items


@transaction.atomic
def award_points_for_response(*, user, response, amount: int, note: str = "") -> PointsTransaction | None:
    if amount <= 0 or user is None:
        return None
    if not user_email_verified(user):
        return None
    if PointsTransaction.objects.filter(
        user=user, response=response, reason=PointsTransaction.Reason.SURVEY_COMPLETION
    ).exists():
        return None
    current = get_points_balance(user)
    new_balance = current + amount
    return PointsTransaction.objects.create(
        user=user,
        amount=amount,
        reason=PointsTransaction.Reason.SURVEY_COMPLETION,
        response=response,
        note=note or f"Completed survey #{response.survey_id}",
        balance_after=new_balance,
    )


@transaction.atomic
def award_xp(
    *,
    user,
    amount: int,
    reason: str,
    response=None,
    note: str = "",
    idempotent_response: bool = False,
) -> XPTransaction | None:
    if not user or amount <= 0:
        return None
    if not user_email_verified(user):
        return None
    if idempotent_response and response is not None:
        if XPTransaction.objects.filter(user=user, response=response, reason=reason).exists():
            return None
    progress = get_or_create_progress(user)
    new_total = progress.xp_total + amount
    new_level = level_for_xp(new_total)
    tx = XPTransaction.objects.create(
        user=user,
        amount=amount,
        reason=reason,
        response=response,
        note=note,
        total_after=new_total,
        level_after=new_level,
    )
    progress.xp_total = new_total
    progress.level = new_level
    progress.save(update_fields=["xp_total", "level", "updated_at"])
    evaluate_badges(user)
    return tx


@transaction.atomic
def award_xp_for_survey_completion(*, user, response) -> XPTransaction | None:
    if not user:
        return None
    if XPTransaction.objects.filter(
        user=user, response=response, reason=XPTransaction.Reason.SURVEY_COMPLETION
    ).exists():
        return None
    progress = get_or_create_progress(user)
    progress.surveys_completed = (progress.surveys_completed or 0) + 1
    progress.save(update_fields=["surveys_completed", "updated_at"])
    return award_xp(
        user=user,
        amount=XP_SURVEY_COMPLETION,
        reason=XPTransaction.Reason.SURVEY_COMPLETION,
        response=response,
        note="Survey completed",
        idempotent_response=True,
    )


@transaction.atomic
def award_xp_for_survey_created(*, user) -> XPTransaction | None:
    if not user:
        return None
    progress = get_or_create_progress(user)
    progress.surveys_created = (progress.surveys_created or 0) + 1
    progress.save(update_fields=["surveys_created", "updated_at"])
    return award_xp(
        user=user, amount=XP_SURVEY_CREATED, reason=XPTransaction.Reason.SURVEY_CREATED
    )


@transaction.atomic
def award_xp_for_profile_complete(*, user) -> XPTransaction | None:
    if not user:
        return None
    if not (user.date_of_birth and user.first_name):
        return None
    if XPTransaction.objects.filter(
        user=user, reason=XPTransaction.Reason.PROFILE_COMPLETE
    ).exists():
        return None
    return award_xp(
        user=user, amount=XP_PROFILE_COMPLETE, reason=XPTransaction.Reason.PROFILE_COMPLETE
    )


@transaction.atomic
def award_xp_for_daily_login(*, user) -> XPTransaction | None:
    if not user:
        return None
    today = timezone.localdate()
    progress = get_or_create_progress(user)
    if progress.last_login_xp_date == today:
        return None
    progress.last_login_xp_date = today
    progress.save(update_fields=["last_login_xp_date", "updated_at"])
    return award_xp(user=user, amount=XP_DAILY_LOGIN, reason=XPTransaction.Reason.DAILY_LOGIN)
