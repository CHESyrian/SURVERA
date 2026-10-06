"""Survey audience targeting helpers."""
from __future__ import annotations

from django.utils.translation import gettext_lazy as _


def normalize_targeting(raw: dict | None) -> dict:
    raw = raw or {}
    genders = raw.get("genders") or []
    if isinstance(genders, str):
        genders = [g.strip() for g in genders.split(",") if g.strip()]
    if not genders and raw.get("gender"):
        g = raw["gender"]
        genders = g if isinstance(g, list) else [g]

    def _int_or(default, key):
        val = raw.get(key)
        if val in (None, ""):
            return default
        try:
            return int(val)
        except (TypeError, ValueError):
            return default

    out = {
        "members_only": bool(raw.get("members_only")),
        "min_level": max(0, _int_or(0, "min_level")),
        "min_age": _int_or(None, "min_age"),
        "max_age": _int_or(None, "max_age"),
        "genders": [str(g).strip().lower() for g in genders if str(g).strip()],
        # min_trust = minimum Reputation level (1–7). 0 = no filter.
        # (JSON key kept for compatibility; value is level, not a separate score.)
        "min_trust": max(0, min(7, _int_or(0, "min_trust"))),
    }
    if (
        out["min_age"] is not None
        and out["max_age"] is not None
        and out["min_age"] > out["max_age"]
    ):
        out["min_age"], out["max_age"] = out["max_age"], out["min_age"]
    return out


def targeting_from_form(cleaned: dict) -> dict:
    members_only = bool(cleaned.get("target_members_only", False))
    if members_only:
        return normalize_targeting(
            {
                "members_only": True,
                "min_level": 0,
                "min_age": None,
                "max_age": None,
                "genders": [],
                "min_trust": 0,
            }
        )
    return normalize_targeting(
        {
            "members_only": False,
            "min_level": cleaned.get("target_min_level") or 0,
            "min_age": cleaned.get("target_min_age"),
            "max_age": cleaned.get("target_max_age"),
            "genders": cleaned.get("target_genders") or [],
            "min_trust": cleaned.get("target_min_trust") or 0,
        }
    )


def has_targeting_rules(targeting: dict | None) -> bool:
    t = normalize_targeting(targeting)
    return any(
        [
            t["members_only"],
            t["min_level"] > 0,
            t["min_age"] is not None,
            t["max_age"] is not None,
            bool(t["genders"]),
            t["min_trust"] > 0,
        ]
    )


def targeting_summary(targeting: dict | None) -> list[str]:
    t = normalize_targeting(targeting)
    lines: list[str] = []
    if t["members_only"]:
        lines.append(str(_("Company members only")))
    if t["min_level"] > 0:
        lines.append(str(_("Minimum level: %(n)s") % {"n": t["min_level"]}))
    if t["min_age"] is not None and t["max_age"] is not None:
        lines.append(str(_("Age: %(a)s–%(b)s") % {"a": t["min_age"], "b": t["max_age"]}))
    elif t["min_age"] is not None:
        lines.append(str(_("Minimum age: %(n)s") % {"n": t["min_age"]}))
    elif t["max_age"] is not None:
        lines.append(str(_("Maximum age: %(n)s") % {"n": t["max_age"]}))
    if t["genders"]:
        lines.append(str(_("Gender: %(g)s") % {"g": ", ".join(t["genders"])}))
    if t["min_trust"] > 0:
        lines.append(
            str(_("Minimum reputation level: %(n)s") % {"n": t["min_trust"]})
        )
    return lines


def user_matches_targeting(user, survey) -> tuple[bool, str]:
    t = normalize_targeting(getattr(survey, "targeting", None))
    if not has_targeting_rules(t):
        return True, ""

    if user is None or not getattr(user, "is_authenticated", False):
        return False, str(_("Please log in to take this survey."))

    if t["members_only"]:
        if not survey.company_id:
            return False, str(_("This survey is restricted to company members."))
        from apps.companies.models import CompanyMembership

        is_member = CompanyMembership.objects.filter(
            company_id=survey.company_id, user=user, is_active=True
        ).exists()
        if not is_member:
            return False, str(_("Only members of this company can take this survey."))

    if t["min_level"] > 0:
        from apps.rewards.services import get_or_create_progress

        progress = get_or_create_progress(user)
        if progress.level < t["min_level"]:
            return False, str(
                _("You need level %(n)s or higher to take this survey.") % {"n": t["min_level"]}
            )

    age = getattr(user, "age", None)
    if t["min_age"] is not None:
        if age is None:
            return False, str(_("Please set your date of birth in your profile."))
        if age < t["min_age"]:
            return False, str(_("You do not meet the minimum age for this survey."))
    if t["max_age"] is not None:
        if age is None:
            return False, str(_("Please set your date of birth in your profile."))
        if age > t["max_age"]:
            return False, str(_("You do not meet the age range for this survey."))

    if t["genders"]:
        g = (user.gender or "").strip().lower()
        if not g:
            return False, str(_("Please set your gender in your profile."))
        if g not in t["genders"]:
            return False, str(_("This survey is targeted to a different audience."))

    if t["min_trust"] > 0:
        # Reputation level is derived from honor_points (same system).
        level = int(getattr(user, "trust_level", None) or 1)
        if level < t["min_trust"]:
            return False, str(
                _(
                    "Your reputation level is too low for this survey. "
                    "You need reputation level %(n)s or higher."
                )
                % {"n": t["min_trust"]}
            )

    return True, ""


def can_access_survey(user, survey) -> tuple[bool, str]:
    from apps.surveys.models import Survey

    if survey.visibility == Survey.Visibility.PRIVATE:
        if user is None or not getattr(user, "is_authenticated", False):
            return False, str(_("This private survey requires login."))
    return user_matches_targeting(user, survey)


def survey_visible_in_discover(survey, user=None) -> bool:
    from apps.surveys.models import Survey

    if survey.visibility == Survey.Visibility.PRIVATE:
        return False
    t = normalize_targeting(getattr(survey, "targeting", None))
    if not t["members_only"]:
        return True
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if not survey.company_id:
        return False
    from apps.companies.models import CompanyMembership

    return CompanyMembership.objects.filter(
        company_id=survey.company_id, user=user, is_active=True
    ).exists()
