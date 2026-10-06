"""Ownership and free/paid rules for surveys."""
from django.utils.translation import gettext_lazy as _

from .models import Survey


def user_manageable_companies(user):
    """Companies where the user can create/manage surveys."""
    if not user or not user.is_authenticated:
        return []
    from apps.companies.models import CompanyMembership

    memberships = CompanyMembership.objects.filter(
        user=user, is_active=True
    ).select_related("company")
    return [m for m in memberships if m.can_manage_surveys]


def can_create_survey(user) -> tuple[bool, str]:
    """Only company managers and project superusers can create surveys."""
    if not user or not user.is_authenticated:
        return False, str(_("Login required."))
    if user.is_superuser:
        return True, ""
    if user_manageable_companies(user):
        return True, ""
    return False, str(
        _("Only company owners/moderators can create surveys. Create or join a company first.")
    )


def apply_free_survey_rules(survey: Survey) -> Survey:
    survey.is_paid = False
    survey.points_reward = 0
    survey.response_target = None
    survey.visibility = Survey.Visibility.PUBLIC
    survey.targeting = {}
    return survey


def apply_survey_pricing_rules(survey: Survey) -> Survey:
    """Company surveys only: free → public/XP-only; paid keeps form values."""
    if not survey.is_paid:
        return apply_free_survey_rules(survey)
    return survey
