"""Daily / weekly task progress and rewards."""
from __future__ import annotations

import logging
from datetime import date

from django.db import transaction
from django.utils import timezone

from apps.rewards.levels import XP_TASK_DAILY, XP_TASK_WEEKLY

logger = logging.getLogger(__name__)

# Seed catalog
DAILY_CODE = "daily_surveys_3"
WEEKLY_CODE = "weekly_surveys_10"
HONOR_TASK_DAILY = 5
HONOR_TASK_WEEKLY = 5


def period_key_daily(d: date | None = None) -> str:
    d = d or timezone.localdate()
    return d.isoformat()


def period_key_weekly(d: date | None = None) -> str:
    d = d or timezone.localdate()
    iso = d.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


@transaction.atomic
def ensure_default_task_definitions() -> None:
    from apps.rewards.models import TaskDefinition

    defaults = [
        {
            "code": DAILY_CODE,
            "kind": TaskDefinition.Kind.DAILY,
            "title": "Complete 3 surveys today",
            "description": "Finish three surveys in a single day.",
            "metric": TaskDefinition.Metric.SURVEYS_COMPLETED,
            "target_count": 3,
            "honor_reward": HONOR_TASK_DAILY,
            "xp_reward": XP_TASK_DAILY,
            "sort_order": 1,
        },
        {
            "code": WEEKLY_CODE,
            "kind": TaskDefinition.Kind.WEEKLY,
            "title": "Complete 10 surveys this week",
            "description": "Finish ten surveys in the current week.",
            "metric": TaskDefinition.Metric.SURVEYS_COMPLETED,
            "target_count": 10,
            "honor_reward": HONOR_TASK_WEEKLY,
            "xp_reward": XP_TASK_WEEKLY,
            "sort_order": 1,
        },
    ]
    for row in defaults:
        TaskDefinition.objects.update_or_create(
            code=row["code"],
            defaults={**{k: v for k, v in row.items() if k != "code"}, "is_active": True},
        )


def _get_or_create_progress(user, definition, period_key):
    from apps.rewards.models import TaskProgress

    progress, _ = TaskProgress.objects.select_for_update().get_or_create(
        user=user,
        definition=definition,
        period_key=period_key,
        defaults={"current_count": 0},
    )
    return progress


@transaction.atomic
def on_survey_completed(*, user, response=None) -> list:
    """
    Increment daily/weekly survey-completion tasks and grant rewards when targets met.
    Returns list of newly completed TaskProgress rows.
    """
    if user is None:
        return []

    ensure_default_task_definitions()
    from apps.rewards.models import TaskDefinition, TaskProgress

    completed_now: list = []
    defs = TaskDefinition.objects.filter(
        is_active=True,
        metric=TaskDefinition.Metric.SURVEYS_COMPLETED,
        kind__in=[TaskDefinition.Kind.DAILY, TaskDefinition.Kind.WEEKLY],
    )

    for definition in defs:
        if definition.kind == TaskDefinition.Kind.DAILY:
            key = period_key_daily()
        elif definition.kind == TaskDefinition.Kind.WEEKLY:
            key = period_key_weekly()
        else:
            key = ""

        progress = _get_or_create_progress(user, definition, key)
        if progress.completed_at:
            continue

        progress.current_count = (progress.current_count or 0) + 1
        update_fields = ["current_count", "updated_at"]
        if progress.current_count >= definition.target_count:
            progress.completed_at = timezone.now()
            update_fields.append("completed_at")
            progress.save(update_fields=update_fields)
            _grant_task_rewards(user=user, definition=definition, progress=progress, response=response)
            completed_now.append(progress)
        else:
            progress.save(update_fields=update_fields)

    return completed_now


def _grant_task_rewards(*, user, definition, progress, response=None) -> None:
    from apps.accounts.honor import apply_honor_delta
    from apps.accounts.models import HonorEvent
    from apps.rewards.models import XPTransaction
    from apps.rewards.services import award_xp

    if definition.honor_reward:
        reason = (
            HonorEvent.Reason.DAILY_GOAL
            if definition.kind == definition.Kind.DAILY
            else HonorEvent.Reason.WEEKLY_GOAL
        )
        try:
            apply_honor_delta(
                user=user,
                amount=int(definition.honor_reward),
                reason=reason,
                note=f"Task {definition.code} period {progress.period_key}",
                once=False,
            )
        except Exception:
            logger.exception("Task honor grant failed user=%s task=%s", user.pk, definition.code)

    if definition.xp_reward:
        xp_reason = (
            XPTransaction.Reason.TASK_DAILY
            if definition.kind == definition.Kind.DAILY
            else XPTransaction.Reason.TASK_WEEKLY
        )
        try:
            award_xp(
                user=user,
                amount=int(definition.xp_reward),
                reason=xp_reason,
                response=response,
                note=f"Task {definition.code}",
            )
        except Exception:
            logger.exception("Task XP grant failed user=%s task=%s", user.pk, definition.code)


def list_user_tasks(user) -> dict:
    """Tasks page payload: daily, weekly, general (empty for now)."""
    ensure_default_task_definitions()
    from apps.rewards.models import TaskDefinition, TaskProgress

    daily_key = period_key_daily()
    weekly_key = period_key_weekly()
    result = {"daily": [], "weekly": [], "general": []}

    for definition in TaskDefinition.objects.filter(is_active=True).order_by("kind", "sort_order"):
        if definition.kind == TaskDefinition.Kind.DAILY:
            key = daily_key
            bucket = "daily"
        elif definition.kind == TaskDefinition.Kind.WEEKLY:
            key = weekly_key
            bucket = "weekly"
        else:
            key = ""
            bucket = "general"

        progress = TaskProgress.objects.filter(
            user=user, definition=definition, period_key=key
        ).first()
        current = progress.current_count if progress else 0
        done = bool(progress and progress.completed_at)
        result[bucket].append(
            {
                "definition": definition,
                "period_key": key,
                "current_count": current,
                "target_count": definition.target_count,
                "is_complete": done,
                "percent": min(100, int(100 * current / definition.target_count))
                if definition.target_count
                else 0,
                "honor_reward": definition.honor_reward,
                "xp_reward": definition.xp_reward,
            }
        )
    return result
