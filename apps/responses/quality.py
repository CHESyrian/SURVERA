"""
Survey response quality scoring (v1).

Produces a 0–100 score from completeness, pace, pattern integrity, and substance.
Maps to tiers and a capped honor grant (separate from paid survey Points).
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.surveys.conditions import visible_questions
from apps.surveys.models import Question

logger = logging.getLogger(__name__)

# Component weights (sum = 1.0)
W_COMPLETENESS = 0.25
W_PACE = 0.25
W_PATTERN = 0.30
W_SUBSTANCE = 0.20

# Honor mapping
HONOR_BY_TIER = {
    "reject": 0,
    "low": 0,
    "standard": 2,
    "high": 4,
}
MAX_HONOR_PER_RESPONSE = 6
MAX_QUALITY_HONOR_PER_DAY = 20
NEWCOMER_HONOR_FACTOR = 0.5  # trust_level == 1 → half quality honor

# Time floors (seconds) by question type
_TIME_FLOOR: dict[str, int] = {
    Question.Type.YES_NO: 2,
    Question.Type.SINGLE_CHOICE: 2,
    Question.Type.MULTIPLE_CHOICE: 3,
    Question.Type.RATING: 2,
    Question.Type.SCALE: 2,
    Question.Type.NUMBER: 2,
    Question.Type.DATE: 2,
    Question.Type.TEXT: 5,
    Question.Type.RANKING: 4,
    Question.Type.MATRIX: 4,
}

_TRIVIAL_TEXT = re.compile(
    r"^(.)\1{2,}$|^(test|asdf|qwerty|xxx|n/?a|na|none|idk|ok|okay|good|fine)\.?$",
    re.I,
)


@dataclass
class QualityResult:
    score: float
    tier: str
    components: dict[str, float]
    flags: list[str] = field(default_factory=list)
    honor_base: int = 0
    honor_granted: int = 0
    expected_min_seconds: float = 0.0
    elapsed_seconds: float | None = None


def expected_min_seconds(questions: list) -> float:
    total = 3.0  # navigation overhead
    for q in questions:
        floor = _TIME_FLOOR.get(q.type, 3)
        cfg = q.config or {}
        if q.type == Question.Type.RANKING:
            items = cfg.get("items") or []
            floor = 2 + max(len(items), 2)
        elif q.type == Question.Type.MATRIX:
            rows = cfg.get("rows") or []
            floor = 2 + max(len(rows), 1)
        elif q.type == Question.Type.TEXT:
            # Slightly longer if help text suggests detail
            floor = 8 if (q.help_text or "").strip() else 5
        total += floor
    return float(total)


def _is_empty(value) -> bool:
    return value in (None, "", [], {})


def score_completeness(visible: list, answers_map: dict) -> tuple[float, list[str]]:
    flags: list[str] = []
    if not visible:
        return 1.0, flags

    required = [q for q in visible if q.is_required]
    optional = [q for q in visible if not q.is_required]

    for q in required:
        if q.id not in answers_map or _is_empty(answers_map.get(q.id)):
            flags.append("missing_required")
            return 0.0, flags

    if not optional:
        return 1.0, flags

    filled = sum(1 for q in optional if q.id in answers_map and not _is_empty(answers_map.get(q.id)))
    fill_rate = filled / len(optional)
    # Required complete → at least 0.7; optional pushes toward 1.0
    return 0.7 + 0.3 * fill_rate, flags


def score_pace(elapsed: float | None, expected: float) -> tuple[float, list[str]]:
    flags: list[str] = []
    if elapsed is None or expected <= 0:
        return 0.85, flags  # neutral if timestamps missing

    ratio = elapsed / expected
    if ratio < 0.25:
        flags.append("speed")
        return 0.0, flags
    if ratio < 0.50:
        flags.append("speed")
        return 0.4, flags
    if ratio < 0.75:
        return 0.7, flags
    if ratio <= 4.0:
        return 1.0, flags
    if ratio <= 8.0:
        return 0.85, flags
    return 0.7, flags


def score_pattern(visible: list, answers_map: dict) -> tuple[float, list[str]]:
    flags: list[str] = []
    score = 1.0

    # Scale / rating values for straight-lining
    scale_vals: list[str] = []
    for q in visible:
        if q.type in {Question.Type.RATING, Question.Type.SCALE, Question.Type.NUMBER}:
            v = answers_map.get(q.id)
            if not _is_empty(v):
                scale_vals.append(str(v))

    if len(scale_vals) >= 4:
        most = max(scale_vals.count(x) for x in set(scale_vals))
        if most / len(scale_vals) >= 0.8:
            score -= 0.35
            flags.append("straight_line")

    # Choice questions: first-option bias
    first_hits = 0
    choice_n = 0
    for q in visible:
        if q.type not in {Question.Type.SINGLE_CHOICE, Question.Type.YES_NO}:
            continue
        choices = (q.config or {}).get("choices") or []
        v = answers_map.get(q.id)
        if _is_empty(v):
            continue
        choice_n += 1
        if q.type == Question.Type.YES_NO:
            # Treat "yes"/true as first bias only if we want — skip yes_no for first-option
            continue
        if choices and (v == choices[0] or str(v) == str(choices[0])):
            first_hits += 1
    if choice_n >= 5 and first_hits / choice_n >= 0.8:
        score -= 0.30
        flags.append("first_option_bias")

    # Alternating pattern on sequential single-choice (simple ABAB)
    seq = []
    for q in sorted(visible, key=lambda x: x.order):
        if q.type == Question.Type.SINGLE_CHOICE:
            v = answers_map.get(q.id)
            if not _is_empty(v):
                seq.append(str(v))
    if len(seq) >= 6:
        abab = all(seq[i] == seq[i % 2] for i in range(len(seq)))
        if abab and seq[0] != seq[1]:
            score -= 0.25
            flags.append("alternating")

    # Matrix uniform column
    for q in visible:
        if q.type != Question.Type.MATRIX:
            continue
        v = answers_map.get(q.id)
        if not isinstance(v, dict) or len(v) < 2:
            continue
        cols = [str(c) for c in v.values()]
        if cols and all(c == cols[0] for c in cols):
            score -= 0.35
            flags.append("matrix_uniform")
            break

    return max(0.0, min(1.0, score)), flags


def score_substance(visible: list, answers_map: dict) -> tuple[float, list[str]]:
    flags: list[str] = []
    parts: list[float] = []

    for q in visible:
        v = answers_map.get(q.id)
        if q.type == Question.Type.TEXT:
            if _is_empty(v):
                continue
            text = str(v).strip()
            if len(text) < 3:
                parts.append(0.2)
                flags.append("thin_text")
            elif _TRIVIAL_TEXT.match(text) or len(set(text.lower())) <= 2:
                parts.append(0.15)
                flags.append("trivial_text")
            elif len(text) < 8:
                parts.append(0.55)
            else:
                parts.append(1.0)
        elif q.type == Question.Type.RANKING:
            if isinstance(v, list) and len(v) >= 2 and len(v) == len(set(str(x) for x in v)):
                parts.append(1.0)
            elif not _is_empty(v):
                parts.append(0.5)
        elif q.type == Question.Type.MATRIX:
            if isinstance(v, dict) and v:
                cols = [str(c) for c in v.values()]
                if len(set(cols)) == 1 and len(cols) > 1:
                    parts.append(0.3)
                else:
                    parts.append(0.9)
        elif q.type in {
            Question.Type.SINGLE_CHOICE,
            Question.Type.MULTIPLE_CHOICE,
            Question.Type.YES_NO,
            Question.Type.RATING,
            Question.Type.SCALE,
            Question.Type.NUMBER,
            Question.Type.DATE,
        }:
            if not _is_empty(v):
                parts.append(0.9)

    if not parts:
        return 0.85, flags
    return sum(parts) / len(parts), flags


def compute_quality_score(
    *,
    questions: list,
    answers_map: dict,
    started_at,
    completed_at,
) -> QualityResult:
    visible = visible_questions(questions, answers_map)
    expected = expected_min_seconds(visible)
    elapsed = None
    if started_at and completed_at:
        elapsed = max(0.0, (completed_at - started_at).total_seconds())

    a, f_a = score_completeness(visible, answers_map)
    b, f_b = score_pace(elapsed, expected)
    c, f_c = score_pattern(visible, answers_map)
    d, f_d = score_substance(visible, answers_map)

    flags = list(dict.fromkeys(f_a + f_b + f_c + f_d))  # unique, stable order
    raw = 100.0 * (W_COMPLETENESS * a + W_PACE * b + W_PATTERN * c + W_SUBSTANCE * d)
    score = round(max(0.0, min(100.0, raw)), 1)

    if score < 30 or "missing_required" in flags:
        tier = "reject"
    elif score < 50:
        tier = "low"
    elif score < 80:
        tier = "standard"
    else:
        tier = "high"

    # Length factor
    n = max(len(visible), 1)
    length_factor = min(1.5, max(0.75, 0.75 + 0.05 * n))
    base = HONOR_BY_TIER[tier]
    honor = int(base * length_factor) if base else 0
    honor = min(honor, MAX_HONOR_PER_RESPONSE)

    return QualityResult(
        score=score,
        tier=tier,
        components={
            "completeness": round(a, 3),
            "pace": round(b, 3),
            "pattern": round(c, 3),
            "substance": round(d, 3),
        },
        flags=flags,
        honor_base=base,
        honor_granted=honor,  # may be reduced by caps later
        expected_min_seconds=expected,
        elapsed_seconds=elapsed,
    )


def _quality_honor_today(user) -> int:
    from apps.accounts.models import HonorEvent

    start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    total = (
        HonorEvent.objects.filter(
            user=user,
            reason=HonorEvent.Reason.SURVEY_QUALITY,
            created_at__gte=start,
            amount__gt=0,
        ).aggregate(s=Sum("amount"))["s"]
        or 0
    )
    return int(total)


@transaction.atomic
def assess_and_reward_response(response) -> Any:
    """
    Score a completed response, persist QualityAssessment, grant honor if due.

    Idempotent per response. Never raises to callers — logs and returns None on failure
    only after best effort; ValueError not used. Safe to call from complete_response.
    """
    from apps.accounts.honor import apply_honor_delta
    from apps.accounts.models import HonorEvent
    from apps.responses.models import QualityAssessment

    if response.status != response.Status.COMPLETED:
        return None
    if QualityAssessment.objects.filter(response=response).exists():
        return QualityAssessment.objects.get(response=response)

    survey = response.survey
    questions = list(survey.questions.all())
    answers_map = {a.question_id: a.value for a in response.answers.all()}

    result = compute_quality_score(
        questions=questions,
        answers_map=answers_map,
        started_at=response.started_at,
        completed_at=response.completed_at or timezone.now(),
    )

    honor = result.honor_granted
    user = response.participant

    if user is not None and honor > 0:
        # Newcomer soft factor
        if int(getattr(user, "trust_level", 1) or 1) <= 1:
            honor = max(0, int(honor * NEWCOMER_HONOR_FACTOR))
        # Daily cap
        already = _quality_honor_today(user)
        remaining = max(0, MAX_QUALITY_HONOR_PER_DAY - already)
        honor = min(honor, remaining)
    else:
        honor = 0

    assessment = QualityAssessment.objects.create(
        response=response,
        survey=survey,
        user=user,
        score=result.score,
        tier=result.tier,
        components=result.components,
        flags=result.flags,
        honor_granted=honor,
        expected_min_seconds=result.expected_min_seconds,
        elapsed_seconds=result.elapsed_seconds,
    )

    if user is not None and honor > 0:
        try:
            apply_honor_delta(
                user=user,
                amount=honor,
                reason=HonorEvent.Reason.SURVEY_QUALITY,
                note=f"Quality {result.tier} ({result.score}) response #{response.pk}",
                once=False,
            )
        except Exception:
            logger.exception(
                "Quality honor grant failed response_id=%s user_id=%s",
                response.pk,
                user.pk,
            )

    return assessment
