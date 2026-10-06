"""Server-side answer validation by question type."""
from __future__ import annotations

from django.utils.translation import gettext_lazy as _

from apps.surveys.conditions import is_question_visible
from apps.surveys.models import Question


def validate_answer(question: Question, value) -> tuple[object | None, str | None]:
    qtype = question.type
    required = question.is_required
    cfg = question.config or {}

    empty = value in (None, "", [], {})
    if empty:
        if required:
            return None, str(_("This question is required."))
        return None, None

    if qtype == Question.Type.SINGLE_CHOICE:
        choices = cfg.get("choices") or []
        if value not in choices and str(value) not in [str(c) for c in choices]:
            return None, str(_("Invalid choice."))
        return value, None

    if qtype == Question.Type.MULTIPLE_CHOICE:
        if not isinstance(value, list):
            value = [value]
        choices = set(cfg.get("choices") or [])
        if not value:
            if required:
                return None, str(_("Select at least one option."))
            return [], None
        for v in value:
            if v not in choices and str(v) not in {str(c) for c in choices}:
                return None, str(_("Invalid choice."))
        return value, None

    if qtype == Question.Type.YES_NO:
        if str(value).lower() not in {"yes", "no", "true", "false", "1", "0"}:
            if value not in (True, False, "Yes", "No"):
                return None, str(_("Answer Yes or No."))
        return value, None

    if qtype in {Question.Type.RATING, Question.Type.SCALE, Question.Type.NUMBER}:
        try:
            num = float(value) if "." in str(value) else int(value)
        except (TypeError, ValueError):
            return None, str(_("Enter a valid number."))
        if qtype == Question.Type.RATING:
            max_v = cfg.get("max", 5)
            if num < 1 or num > max_v:
                return None, str(_("Rating out of range."))
        if qtype == Question.Type.SCALE:
            min_v, max_v = cfg.get("min", 1), cfg.get("max", 10)
            if num < min_v or num > max_v:
                return None, str(_("Value out of range."))
        return num, None

    if qtype == Question.Type.RANKING:
        if not isinstance(value, list) or len(value) < 1:
            return None, str(_("Provide a ranking."))
        return value, None

    if qtype == Question.Type.MATRIX:
        if not isinstance(value, dict):
            return None, str(_("Invalid matrix answer."))
        return value, None

    return value, None


def validate_all_answers(questions, raw_answers: dict) -> tuple[dict, dict]:
    """Return (normalized, errors) respecting conditional visibility."""
    # First pass for visibility without required enforcement
    soft = {}
    for q in questions:
        val = raw_answers.get(q.id)
        soft[q.id] = val

    normalized = {}
    errors = {}
    for q in questions:
        if not is_question_visible(q, soft):
            continue
        val, err = validate_answer(q, raw_answers.get(q.id))
        if err:
            errors[q.id] = err
        elif val is not None:
            normalized[q.id] = val
    return normalized, errors
