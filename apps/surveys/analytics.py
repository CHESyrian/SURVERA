"""Survey analytics aggregates for manager dashboards."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import timedelta
from typing import Any

from django.db.models import Count
from django.db.models.functions import TruncDate
from django.utils import timezone

from apps.responses.models import Answer, Response
from apps.surveys.models import Question, Survey


def _with_bar_metrics(items: list[dict], *, total: int) -> list[dict]:
    """Add percent and bar_pct (0–100 width) for horizontal bar charts."""
    peak = max((int(i.get("count") or 0) for i in items), default=0)
    for i in items:
        c = int(i.get("count") or 0)
        i["percent"] = round(100.0 * c / total, 1) if total else 0.0
        if peak <= 0 or c <= 0:
            i["bar_pct"] = 0
        else:
            i["bar_pct"] = max(4, int(round(100 * c / peak)))
    return items


def get_survey_analytics(survey: Survey, *, days: int = 14) -> dict[str, Any]:
    """
    Return summary stats, daily completed counts, and per-question breakdowns.

    Safe to call from views; does not enforce permissions.
    """
    responses = Response.objects.filter(survey=survey)
    total = responses.count()
    completed = responses.filter(status=Response.Status.COMPLETED).count()
    in_progress = responses.filter(status=Response.Status.IN_PROGRESS).count()
    abandoned = max(0, total - completed - in_progress)
    completion_rate = round(100.0 * completed / total, 1) if total else 0.0

    target = survey.response_target
    target_pct = (
        round(100.0 * completed / target, 1) if target and target > 0 else None
    )

    daily = _daily_completed_counts(survey, days=days)
    question_stats = [
        _question_summary(q)
        for q in survey.questions.all().order_by("order", "id")
    ]

    # SVG donut segments for status mix (completed / in progress / other)
    status_chart = _status_donut(completed=completed, in_progress=in_progress, other=abandoned)

    return {
        "survey": survey,
        "total": total,
        "completed": completed,
        "in_progress": in_progress,
        "abandoned": abandoned,
        "completion_rate": completion_rate,
        "response_target": target,
        "target_pct": target_pct,
        "daily_completed": daily,
        "question_stats": question_stats,
        "days": days,
        "status_chart": status_chart,
    }


def _status_donut(*, completed: int, in_progress: int, other: int) -> dict[str, Any]:
    """Build SVG stroke-dasharray segments for a simple donut chart."""
    total = completed + in_progress + other
    circumference = 100  # use percentage units on a circle r≈15.9155
    if total <= 0:
        return {
            "total": 0,
            "segments": [
                {"key": "empty", "value": 0, "pct": 0, "dash": "0 100", "offset": 0},
            ],
        }
    parts = [
        ("completed", completed),
        ("in_progress", in_progress),
        ("other", other),
    ]
    segments = []
    offset = 0.0
    for key, value in parts:
        pct = 100.0 * value / total
        dash = f"{pct:.2f} {circumference - pct:.2f}"
        segments.append(
            {
                "key": key,
                "value": value,
                "pct": round(pct, 1),
                "dash": dash,
                "offset": round(-offset, 2),
            }
        )
        offset += pct
    return {"total": total, "segments": segments}


def _daily_completed_counts(survey: Survey, *, days: int) -> list[dict[str, Any]]:
    since = timezone.now() - timedelta(days=days - 1)
    rows = (
        Response.objects.filter(
            survey=survey,
            status=Response.Status.COMPLETED,
            completed_at__gte=since,
        )
        .annotate(day=TruncDate("completed_at"))
        .values("day")
        .annotate(count=Count("id"))
        .order_by("day")
    )
    by_day = {r["day"]: r["count"] for r in rows if r["day"] is not None}

    out: list[dict[str, Any]] = []
    today = timezone.localdate()
    counts = [by_day.get(today - timedelta(days=i), 0) for i in range(days - 1, -1, -1)]
    peak = max(counts) if counts else 0
    for i, c in enumerate(counts):
        d = today - timedelta(days=days - 1 - i)
        # Bar height in px for simple CSS chart (2–96)
        if peak <= 0 or c <= 0:
            height = 2
        else:
            height = max(4, int(round(96 * c / peak)))
        out.append({"date": d, "count": c, "bar_height": height})
    return out


def _question_summary(question: Question) -> dict[str, Any]:
    answers = list(
        Answer.objects.filter(
            question=question,
            response__status=Response.Status.COMPLETED,
        ).values_list("value", flat=True)
    )
    answer_count = len(answers)
    breakdown = _value_breakdown(question, answers)
    return {
        "question": question,
        "answer_count": answer_count,
        "breakdown": breakdown,
    }


def _value_breakdown(question: Question, values: list) -> dict[str, Any] | None:
    """Return type-specific aggregates; None when only a count is useful (text)."""
    qtype = question.type
    cfg = question.config or {}

    if qtype in {
        Question.Type.SINGLE_CHOICE,
        Question.Type.YES_NO,
        Question.Type.RATING,
        Question.Type.SCALE,
        Question.Type.NUMBER,
    }:
        counter: Counter = Counter()
        numeric: list[float] = []
        for v in values:
            if qtype in {Question.Type.RATING, Question.Type.SCALE, Question.Type.NUMBER}:
                try:
                    num = float(v)
                    numeric.append(num)
                    counter[str(int(num) if num == int(num) else num)] += 1
                except (TypeError, ValueError):
                    counter[str(v)] += 1
            else:
                # yes/no / single choice
                key = str(v).strip().lower() if qtype == Question.Type.YES_NO else str(v)
                if qtype == Question.Type.YES_NO:
                    if key in {"true", "1", "yes"}:
                        key = "yes"
                    elif key in {"false", "0", "no"}:
                        key = "no"
                counter[key] += 1

        items = [{"label": k, "count": c} for k, c in counter.most_common()]
        dist_total = sum(counter.values()) or 0
        items = _with_bar_metrics(items, total=dist_total)
        result: dict[str, Any] = {"kind": "distribution", "items": items}
        if numeric:
            result["avg"] = round(sum(numeric) / len(numeric), 2)
            result["min"] = min(numeric)
            result["max"] = max(numeric)
        if qtype in {Question.Type.SINGLE_CHOICE}:
            # Preserve declared choice order when possible
            choices = cfg.get("choices") or []
            order = {str(c): i for i, c in enumerate(choices)}
            items.sort(key=lambda x: order.get(x["label"], 999))
            result["items"] = items
        return result

    if qtype == Question.Type.MULTIPLE_CHOICE:
        counter = Counter()
        for v in values:
            opts = v if isinstance(v, list) else [v]
            for o in opts:
                counter[str(o)] += 1
        items = [{"label": k, "count": c} for k, c in counter.most_common()]
        choices = cfg.get("choices") or []
        order = {str(c): i for i, c in enumerate(choices)}
        items.sort(key=lambda x: order.get(x["label"], 999))
        items = _with_bar_metrics(items, total=sum(counter.values()) or 0)
        return {"kind": "distribution", "items": items}

    if qtype == Question.Type.RANKING:
        # Average rank position per item (1 = top)
        rank_sums: dict[str, float] = defaultdict(float)
        rank_counts: dict[str, int] = defaultdict(int)
        for v in values:
            if not isinstance(v, list):
                continue
            for pos, item in enumerate(v, start=1):
                key = str(item)
                rank_sums[key] += pos
                rank_counts[key] += 1
        items = [
            {
                "label": k,
                "avg_rank": round(rank_sums[k] / rank_counts[k], 2),
                "count": rank_counts[k],
            }
            for k in rank_sums
        ]
        items.sort(key=lambda x: x["avg_rank"])
        # Invert rank for bar width: lower avg_rank → longer bar
        if items:
            worst = max(i["avg_rank"] for i in items) or 1
            for i in items:
                # Higher score = better (closer to rank 1)
                score = (worst + 1) - i["avg_rank"]
                i["bar_pct"] = max(4, int(round(100 * score / worst))) if worst else 0
        return {"kind": "ranking", "items": items}

    if qtype == Question.Type.MATRIX:
        # Count cell selections: row -> col -> count
        cell: dict[str, Counter] = defaultdict(Counter)
        for v in values:
            if not isinstance(v, dict):
                continue
            for row, col in v.items():
                cell[str(row)][str(col)] += 1
        rows = []
        for row, cols in cell.items():
            rows.append(
                {
                    "row": row,
                    "columns": [{"label": c, "count": n} for c, n in cols.most_common()],
                }
            )
        return {"kind": "matrix", "rows": rows}

    # text / date / unknown — count only
    return {"kind": "count_only"}
