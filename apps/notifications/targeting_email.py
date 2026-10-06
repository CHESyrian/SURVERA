"""Rules for when survey-publish emails should be sent."""
from __future__ import annotations


def should_email_survey_published(survey) -> bool:
    """
    Email only high-intent audiences to avoid spam:

    - private surveys, or
    - members_only targeting
    """
    from apps.surveys.models import Survey

    if getattr(survey, "visibility", None) == Survey.Visibility.PRIVATE:
        return True
    targeting = getattr(survey, "targeting", None) or {}
    if targeting.get("members_only"):
        return True
    return False
