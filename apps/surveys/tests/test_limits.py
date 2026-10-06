"""Tests for can_create_survey and free/paid pricing rules."""
import pytest

from apps.factories import CompanyMembershipFactory, SurveyFactory, UserFactory
from apps.companies.models import CompanyMembership
from apps.surveys.limits import (
    apply_free_survey_rules,
    apply_survey_pricing_rules,
    can_create_survey,
    user_manageable_companies,
)
from apps.surveys.models import Survey


@pytest.mark.django_db
class TestCanCreateSurvey:
    def test_anonymous_cannot(self):
        from django.contrib.auth.models import AnonymousUser

        ok, msg = can_create_survey(AnonymousUser())
        assert ok is False

    def test_person_without_membership_cannot(self, person):
        ok, msg = can_create_survey(person)
        assert ok is False
        assert "owner" in msg.lower() or "moderator" in msg.lower() or "company" in msg.lower()

    def test_owner_can(self, owner, company, owner_membership):
        ok, msg = can_create_survey(owner)
        assert ok is True
        assert msg == ""

    def test_moderator_can(self, moderator, company, moderator_membership):
        ok, msg = can_create_survey(moderator)
        assert ok is True

    def test_participant_cannot(self, participant, company, participant_membership):
        ok, msg = can_create_survey(participant)
        assert ok is False

    def test_superuser_can(self, db):
        su = UserFactory(is_superuser=True)
        ok, msg = can_create_survey(su)
        assert ok is True

    def test_user_manageable_companies_only_managers(self, company, owner, owner_membership, participant, participant_membership):
        managed = user_manageable_companies(owner)
        assert any(m.company_id == company.pk for m in managed)
        managed_p = user_manageable_companies(participant)
        assert managed_p == []


@pytest.mark.django_db
class TestPricingRules:
    def test_free_rules_clear_points_and_targeting(self, company, owner):
        survey = SurveyFactory(
            company=company,
            created_by=owner,
            is_paid=True,
            points_reward=100,
            visibility=Survey.Visibility.PRIVATE,
            targeting={"members_only": True},
        )
        apply_free_survey_rules(survey)
        assert survey.is_paid is False
        assert survey.points_reward == 0
        assert survey.visibility == Survey.Visibility.PUBLIC
        assert survey.targeting == {}

    def test_apply_pricing_rules_on_free(self, company, owner):
        survey = SurveyFactory(
            company=company,
            created_by=owner,
            is_paid=False,
            points_reward=50,
            visibility=Survey.Visibility.PRIVATE,
            targeting={"min_level": 3},
        )
        apply_survey_pricing_rules(survey)
        assert survey.is_paid is False
        assert survey.points_reward == 0
        assert survey.visibility == Survey.Visibility.PUBLIC
        assert survey.targeting == {}

    def test_apply_pricing_rules_on_paid_keeps_values(self, company, owner):
        survey = SurveyFactory(
            company=company,
            created_by=owner,
            is_paid=True,
            points_reward=75,
            visibility=Survey.Visibility.PRIVATE,
            targeting={"members_only": True},
        )
        apply_survey_pricing_rules(survey)
        assert survey.is_paid is True
        assert survey.points_reward == 75
        assert survey.visibility == Survey.Visibility.PRIVATE
        assert survey.targeting.get("members_only") is True
