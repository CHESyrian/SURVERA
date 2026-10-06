"""Conditional question visibility."""
from __future__ import annotations


def _normalize_id(key):
    """Coerce source_id / answers_map keys to int when possible."""
    try:
        return int(key)
    except (TypeError, ValueError):
        return key


def _values_equal(a, b) -> bool:
    """Loose equality: numbers, case-insensitive strings (Yes/yes)."""
    if a == b:
        return True
    if a is None or b is None:
        return False
    try:
        if float(a) == float(b):
            return True
    except (TypeError, ValueError):
        pass
    return str(a).strip().lower() == str(b).strip().lower()


def _match(rule: dict, answers_map: dict) -> bool:
    source_id = _normalize_id(rule.get("source_id"))
    op = rule.get("op", "eq")
    expected = rule.get("value")
    # answers_map may use int or str keys
    answered = source_id in answers_map or str(source_id) in answers_map
    value = answers_map.get(source_id, answers_map.get(str(source_id)))

    if op == "answered":
        return answered and value not in (None, "", [], {})
    if op == "not_answered":
        return not answered or value in (None, "", [], {})
    if not answered:
        return False

    if op == "eq":
        return _values_equal(value, expected)
    if op == "neq":
        return not _values_equal(value, expected)
    if op == "in":
        options = expected if isinstance(expected, list) else [expected]
        if isinstance(value, list):
            return any(
                any(_values_equal(v, o) for o in options) for v in value
            )
        return any(_values_equal(value, o) for o in options)
    if op == "not_in":
        options = expected if isinstance(expected, list) else [expected]
        if isinstance(value, list):
            return not any(
                any(_values_equal(v, o) for o in options) for v in value
            )
        return not any(_values_equal(value, o) for o in options)
    if op == "gte":
        try:
            return float(value) >= float(expected)
        except (TypeError, ValueError):
            return False
    if op == "lte":
        try:
            return float(value) <= float(expected)
        except (TypeError, ValueError):
            return False
    return True


def is_question_visible(question, answers_map: dict) -> bool:
    rules = question.conditions or []
    if not rules:
        return True
    return all(_match(r, answers_map) for r in rules)


def visible_questions(questions, answers_map: dict) -> list:
    return [q for q in questions if is_question_visible(q, answers_map)]


def conditions_payload(questions) -> list[dict]:
    payload = []
    for q in questions:
        payload.append(
            {
                "id": q.id,
                "conditions": q.conditions or [],
            }
        )
    return payload
