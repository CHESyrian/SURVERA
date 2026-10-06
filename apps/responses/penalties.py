"""
Report review outcomes: apply penalty catalog or dismiss, then notify parties.

Penalty catalog
---------------
* warning (progressive ladder on the reported user):
    1st → −100 honor + notify
    2nd → −200 honor + notify
    3rd → freeze 7 days + notify
    4th → freeze 30 days + notify
    5th+ → permanent account closure + notify
* honor_deduction — admin chooses honor amount
* rank_reduction — admin chooses how many trust levels to drop
* account_freeze — admin chooses freeze duration (days)
* account_closure — permanent close

Admin control panel is the primary entry point.
"""
from __future__ import annotations

import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

logger = logging.getLogger(__name__)

# Progressive warning ladder
WARNING_1_HONOR = 100
WARNING_2_HONOR = 200
WARNING_3_FREEZE_DAYS = 7
WARNING_4_FREEZE_DAYS = 30


def _freeze_user(*, user, days: int, admin_user=None, note: str = "") -> None:
    """Extend or set frozen_until to now + days (does not clear permanent close)."""
    from apps.accounts.models import User

    days = max(1, int(days))
    user = User.objects.select_for_update().get(pk=user.pk)
    until = timezone.now() + timedelta(days=days)
    # If already frozen further into the future, keep the later date
    if user.frozen_until and user.frozen_until > until:
        until = user.frozen_until
    user.frozen_until = until
    user.save(update_fields=["frozen_until"])
    logger.info("User %s frozen until %s (%s)", user.pk, until, note)


def _close_user_permanently(*, user, admin_user=None, note: str = "") -> None:
    from apps.accounts.models import User

    user = User.objects.select_for_update().get(pk=user.pk)
    user.closed_at = timezone.now()
    user.is_active = False
    user.frozen_until = None
    user.save(update_fields=["closed_at", "is_active", "frozen_until"])
    logger.info("User %s permanently closed (%s)", user.pk, note)


@transaction.atomic
def execute_penalty(*, report, admin_user) -> dict:
    """
    Apply the penalty catalog entry stored on the report.
    Idempotent if penalty_executed_at is already set.
    """
    from apps.accounts.honor import apply_honor_delta, reduce_rank_levels
    from apps.accounts.models import HonorEvent, User
    from apps.responses.models import Report
    from apps.rewards.models import PointsTransaction
    from apps.rewards.services import get_points_balance

    summary: dict = {
        "kind": report.penalty_kind,
        "honor_deducted": 0,
        "points_deducted": 0,
        "rank_from": None,
        "rank_to": None,
        "warning_number": None,
        "frozen_until": None,
        "permanently_closed": False,
        "warning_only": False,
    }

    if report.penalty_executed_at:
        return summary

    user = report.reported_user
    if user is None:
        report.penalty_executed_at = timezone.now()
        report.save(update_fields=["penalty_executed_at", "updated_at"])
        return summary

    note = f"Report #{report.pk} ({report.get_type_display()})"
    if report.resolution_note:
        note = f"{note}: {report.resolution_note[:200]}"

    kind = report.penalty_kind

    # ----- Progressive warning ladder -----
    if kind == Report.PenaltyKind.WARNING:
        user = User.objects.select_for_update().get(pk=user.pk)
        user.warning_count = int(user.warning_count or 0) + 1
        user.save(update_fields=["warning_count"])
        n = user.warning_count
        summary["warning_number"] = n
        report.warning_number = n

        if n == 1:
            apply_honor_delta(
                user=user,
                amount=-WARNING_1_HONOR,
                reason=HonorEvent.Reason.WARNING,
                note=note,
                created_by=admin_user,
            )
            summary["honor_deducted"] = WARNING_1_HONOR
            report.penalty_reputation = WARNING_1_HONOR
        elif n == 2:
            apply_honor_delta(
                user=user,
                amount=-WARNING_2_HONOR,
                reason=HonorEvent.Reason.WARNING,
                note=note,
                created_by=admin_user,
            )
            summary["honor_deducted"] = WARNING_2_HONOR
            report.penalty_reputation = WARNING_2_HONOR
        elif n == 3:
            _freeze_user(user=user, days=WARNING_3_FREEZE_DAYS, admin_user=admin_user, note=note)
            user.refresh_from_db()
            summary["frozen_until"] = user.frozen_until
            report.penalty_freeze_days = WARNING_3_FREEZE_DAYS
        elif n == 4:
            _freeze_user(user=user, days=WARNING_4_FREEZE_DAYS, admin_user=admin_user, note=note)
            user.refresh_from_db()
            summary["frozen_until"] = user.frozen_until
            report.penalty_freeze_days = WARNING_4_FREEZE_DAYS
        else:  # 5+
            _close_user_permanently(user=user, admin_user=admin_user, note=note)
            summary["permanently_closed"] = True

    # ----- Admin-chosen honor deduction -----
    elif kind in {
        Report.PenaltyKind.HONOR_DEDUCTION,
        Report.PenaltyKind.REPUTATION,  # legacy
    }:
        amount = int(report.penalty_reputation or 0)
        if amount > 0:
            apply_honor_delta(
                user=user,
                amount=-amount,
                reason=HonorEvent.Reason.REPORT_PENALTY,
                note=note,
                created_by=admin_user,
            )
            summary["honor_deducted"] = amount

    # ----- Rank reduction -----
    elif kind == Report.PenaltyKind.RANK_REDUCTION:
        levels = max(1, int(report.penalty_rank_levels or 1))
        user.refresh_from_db()
        summary["rank_from"] = int(user.trust_level or 1)
        reduce_rank_levels(
            user=user,
            levels=levels,
            reason=HonorEvent.Reason.REPORT_PENALTY,
            note=note,
            created_by=admin_user,
        )
        user.refresh_from_db()
        summary["rank_to"] = int(user.trust_level or 1)
        summary["honor_deducted"] = max(
            0, (summary["rank_from"] and 0) or 0
        )  # actual delta is in HonorEvent

    # ----- Account freeze (admin days) -----
    elif kind == Report.PenaltyKind.ACCOUNT_FREEZE:
        days = max(1, int(report.penalty_freeze_days or 1))
        _freeze_user(user=user, days=days, admin_user=admin_user, note=note)
        user.refresh_from_db()
        summary["frozen_until"] = user.frozen_until
        report.penalty_freeze_days = days

    # ----- Permanent closure -----
    elif kind == Report.PenaltyKind.ACCOUNT_CLOSURE:
        _close_user_permanently(user=user, admin_user=admin_user, note=note)
        summary["permanently_closed"] = True

    # ----- Legacy survey points / both -----
    elif kind in {Report.PenaltyKind.POINTS, Report.PenaltyKind.BOTH}:
        if kind == Report.PenaltyKind.BOTH and report.penalty_reputation:
            apply_honor_delta(
                user=user,
                amount=-int(report.penalty_reputation),
                reason=HonorEvent.Reason.REPORT_PENALTY,
                note=note,
                created_by=admin_user,
            )
            summary["honor_deducted"] = int(report.penalty_reputation)
        if report.penalty_points > 0:
            current = get_points_balance(user)
            deduct = min(int(report.penalty_points), max(0, current))
            if deduct > 0:
                PointsTransaction.objects.create(
                    user=user,
                    amount=-deduct,
                    reason=PointsTransaction.Reason.ADJUSTMENT,
                    response=report.response,
                    note=note[:255],
                    balance_after=current - deduct,
                )
                summary["points_deducted"] = deduct

    report.penalty_executed_at = timezone.now()
    report.save(
        update_fields=[
            "penalty_executed_at",
            "penalty_reputation",
            "penalty_freeze_days",
            "warning_number",
            "updated_at",
        ]
    )
    return summary


def _notify_report_outcome(*, report, outcome: str, penalty_summary: dict | None = None) -> None:
    """In-app + email to reporter always; subject when penalized."""
    from apps.notifications.email import absolute_url, send_notification_email
    from apps.notifications.models import Notification
    from apps.notifications.services import notify_user

    penalty_summary = penalty_summary or {}
    survey_title = getattr(report.survey, "title", "") or f"Survey #{report.survey_id}"
    resolution = (report.resolution_note or "").strip()

    def _subject_body() -> str:
        parts = [
            str(
                _("A report on your response to “%(survey)s” was upheld.")
                % {"survey": survey_title}
            )
        ]
        kind = penalty_summary.get("kind") or report.penalty_kind
        wn = penalty_summary.get("warning_number")
        if kind == "warning" and wn:
            parts.append(str(_("This is formal warning #%(n)s.") % {"n": wn}))
        if penalty_summary.get("honor_deducted"):
            parts.append(
                str(
                    _("Honor points deducted: %(n)s")
                    % {"n": penalty_summary["honor_deducted"]}
                )
            )
        if penalty_summary.get("rank_from") and penalty_summary.get("rank_to"):
            parts.append(
                str(
                    _("Trust rank reduced: %(a)s → %(b)s")
                    % {
                        "a": penalty_summary["rank_from"],
                        "b": penalty_summary["rank_to"],
                    }
                )
            )
        if penalty_summary.get("frozen_until"):
            parts.append(
                str(
                    _("Account frozen until %(when)s.")
                    % {"when": penalty_summary["frozen_until"]}
                )
            )
        if penalty_summary.get("permanently_closed"):
            parts.append(str(_("Your account has been permanently closed.")))
        if penalty_summary.get("points_deducted"):
            parts.append(
                str(
                    _("Survey points deducted: %(n)s")
                    % {"n": penalty_summary["points_deducted"]}
                )
            )
        if resolution:
            parts.append(resolution)
        return "\n".join(parts)

    # --- Reporter ---
    if report.reporter_id:
        if outcome == "dismissed":
            title = _("Report reviewed — no action taken")
            body = _(
                "Your report on “%(survey)s” was reviewed and dismissed. "
                "No penalty was applied."
            ) % {"survey": survey_title}
        else:
            title = _("Report reviewed — penalty applied")
            body = _(
                "Your report on “%(survey)s” was reviewed. A penalty was applied to the respondent."
            ) % {"survey": survey_title}
        if resolution:
            body = f"{body}\n\n{resolution}"

        try:
            notify_user(
                user=report.reporter,
                type=Notification.Type.SYSTEM,
                title=str(title)[:200],
                body=str(body),
                link="",
                payload={"report_id": report.pk, "outcome": outcome},
            )
        except Exception:
            logger.exception("In-app notify reporter failed report=%s", report.pk)

        try:
            send_notification_email(
                to_email=getattr(report.reporter, "email", "") or "",
                subject=f"SURVERA: {title}"[:200],
                template_name="notifications/email/report_outcome.html",
                context={
                    "user": report.reporter,
                    "role": "reporter",
                    "outcome": outcome,
                    "survey_title": survey_title,
                    "report_type": report.get_type_display(),
                    "resolution_note": resolution,
                    "penalty_summary": penalty_summary,
                    "action_url": absolute_url("/"),
                },
            )
        except Exception:
            logger.exception("Email notify reporter failed report=%s", report.pk)

    # --- Subject ---
    if outcome == "penalized" and report.reported_user_id:
        title = _("Account review — penalty applied")
        body = _subject_body()
        try:
            notify_user(
                user=report.reported_user,
                type=Notification.Type.SYSTEM,
                title=str(title)[:200],
                body=body,
                link="",
                payload={"report_id": report.pk, "outcome": outcome},
            )
        except Exception:
            logger.exception("In-app notify subject failed report=%s", report.pk)

        try:
            send_notification_email(
                to_email=getattr(report.reported_user, "email", "") or "",
                subject=f"SURVERA: {title}"[:200],
                template_name="notifications/email/report_outcome.html",
                context={
                    "user": report.reported_user,
                    "role": "subject",
                    "outcome": outcome,
                    "survey_title": survey_title,
                    "report_type": report.get_type_display(),
                    "resolution_note": resolution,
                    "penalty_summary": penalty_summary,
                    "action_url": absolute_url("/accounts/profile/"),
                },
            )
        except Exception:
            logger.exception("Email notify subject failed report=%s", report.pk)


@transaction.atomic
def resolve_with_penalty(
    *,
    report,
    admin_user,
    penalty_kind: str = "warning",
    penalty_reputation: int = 0,
    penalty_points: int = 0,
    penalty_rank_levels: int = 1,
    penalty_freeze_days: int = 0,
    resolution_note: str = "",
) -> object:
    """Admin decision: apply a catalog penalty, execute it, notify both parties."""
    from apps.responses.models import Report

    # Lock Report only — do not combine select_for_update with select_related on
    # nullable FKs (creates OUTER JOINs; PostgreSQL rejects FOR UPDATE on them).
    report = Report.objects.select_for_update().get(pk=report.pk)
    if not report.is_open:
        raise ValueError("This report has already been closed.")

    kind = (penalty_kind or Report.PenaltyKind.WARNING).strip()
    if kind == Report.PenaltyKind.NONE:
        kind = Report.PenaltyKind.WARNING

    report.penalty_kind = kind
    report.penalty_reputation = max(0, int(penalty_reputation or 0))
    report.penalty_points = max(0, int(penalty_points or 0))
    report.penalty_rank_levels = max(1, int(penalty_rank_levels or 1))
    report.penalty_freeze_days = max(0, int(penalty_freeze_days or 0))
    report.resolution_note = (resolution_note or "").strip()
    report.status = Report.Status.RESOLVED
    report.resolved_by = admin_user
    report.resolved_at = timezone.now()
    report.save(
        update_fields=[
            "penalty_kind",
            "penalty_reputation",
            "penalty_points",
            "penalty_rank_levels",
            "penalty_freeze_days",
            "resolution_note",
            "status",
            "resolved_by",
            "resolved_at",
            "updated_at",
        ]
    )

    summary = execute_penalty(report=report, admin_user=admin_user)
    # Load relations for notifications (no row lock needed on joined tables)
    report = (
        Report.objects.select_related("reporter", "reported_user", "survey", "response")
        .get(pk=report.pk)
    )
    _notify_report_outcome(report=report, outcome="penalized", penalty_summary=summary)
    return report


@transaction.atomic
def dismiss_report(
    *,
    report,
    admin_user,
    resolution_note: str = "",
) -> object:
    """Admin decision: reject report, no penalty. Notify reporter only."""
    from apps.responses.models import Report

    report = Report.objects.select_for_update().get(pk=report.pk)
    if not report.is_open:
        raise ValueError("This report has already been closed.")

    report.penalty_kind = Report.PenaltyKind.NONE
    report.penalty_reputation = 0
    report.penalty_points = 0
    report.penalty_rank_levels = 1
    report.penalty_freeze_days = 0
    report.resolution_note = (resolution_note or "").strip()
    report.status = Report.Status.DISMISSED
    report.resolved_by = admin_user
    report.resolved_at = timezone.now()
    report.save(
        update_fields=[
            "penalty_kind",
            "penalty_reputation",
            "penalty_points",
            "penalty_rank_levels",
            "penalty_freeze_days",
            "resolution_note",
            "status",
            "resolved_by",
            "resolved_at",
            "updated_at",
        ]
    )
    report = (
        Report.objects.select_related("reporter", "reported_user", "survey", "response")
        .get(pk=report.pk)
    )
    _notify_report_outcome(report=report, outcome="dismissed", penalty_summary={})
    return report
