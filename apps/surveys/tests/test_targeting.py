"""Tests for targeting helpers and can_access_survey."""
from datetime import date

import pytest

from apps.factories import CompanyMembershipFactory, SurveyFactory, UserFactory
from apps.companies.models import CompanyMembership
from apps.rewards.models import UserProgress
from apps.surveys.models import Survey
from apps.surveys.targeting import (
    can_access_survey,
    has_targeting_rules,
    normalize_targeting,
    survey_visible_in_discover,
    user_matches_targeting,
)


@pytest.mark.django_db
class TestNormalizeTargeting:
    def test_empty_defaults(self):
        t = normalize_targeting({})
        assert t["members_only"] is False
        assert t["min_level"] == 0
        assert t["min_age"] is None
        assert t["max_age"] is None
        assert t["genders"] == []
        assert t["min_trust"] == 0

    def test_swaps_inverted_age_range(self):
        t = normalize_targeting({"min_age": 40, "max_age": 20})
        assert t["min_age"] == 20
        assert t["max_age"] == 40

    def test_genders_normalized_lowercase(self):
        t = normalize_targeting({"genders": ["Female", "MALE"]})
        assert t["genders"] == ["female", "male"]

    def test_has_targeting_rules_true_when_any_set(self):
        assert has_targeting_rules({"members_only": True}) is True
        assert has_targeting_rules({"min_level": 2}) is True
        assert has_targeting_rules({"genders": ["female"]}) is True
        assert has_targeting_rules({}) is False


@pytest.mark.django_db
class TestCanAccessSurvey:
    def test_public_no_targeting_allows_anonymous(self, company, owner):
        survey = SurveyFactory(
            company=company,
            created_by=owner,
            visibility=Survey.Visibility.PUBLIC,
            targeting={},
        )
        ok, reason = can_access_survey(None, survey)
        assert ok is True
        assert reason == ""

    def test_private_requires_login(self, company, owner):
        survey = SurveyFactory(
            company=company,
            created_by=owner,
            visibility=Survey.Visibility.PRIVATE,
            targeting={},
        )
        ok, reason = can_access_survey(None, survey)
        assert ok is False
        assert "login" in reason.lower() or "private" in reason.lower()

    def test_private_authenticated_without_extra_rules_allowed(self, company, owner, person):
        survey = SurveyFactory(
            company=company,
            created_by=owner,
            visibility=Survey.Visibility.PRIVATE,
            targeting={},
        )
        ok, reason = can_access_survey(person, survey)
        assert ok is True

    def test_members_only_blocks_non_member(self, company, owner, person):
        survey = SurveyFactory(
            company=company,
            created_by=owner,
            visibility=Survey.Visibility.PUBLIC,
            targeting={"members_only": True},
        )
        ok, reason = can_access_survey(person, survey)
        assert ok is False
        assert "member" in reason.lower()

    def test_members_only_allows_active_member(
        self, company, owner, participant, participant_membership
    ):
        survey = SurveyFactory(
            company=company,
            created_by=owner,
            visibility=Survey.Visibility.PUBLIC,
            targeting={"members_only": True},
        )
        ok, reason = can_access_survey(participant, survey)
        assert ok is True

    def test_min_level_blocks_low_level(self, company, owner, person):
        UserProgress.objects.create(user=person, xp_total=0, level=1)
        survey = SurveyFactory(
            company=company,
            created_by=owner,
            visibility=Survey.Visibility.PUBLIC,
            targeting={"min_level": 5},
        )
        ok, reason = can_access_survey(person, survey)
        assert ok is False
        assert "level" in reason.lower()

    def test_min_level_allows_high_enough(self, company, owner, person):
        UserProgress.objects.create(user=person, xp_total=1000, level=10)
        survey = SurveyFactory(
            company=company,
            created_by=owner,
            visibility=Survey.Visibility.PUBLIC,
            targeting={"min_level": 5},
        )
        ok, reason = can_access_survey(person, survey)
        assert ok is True

    def test_age_range_blocks_out_of_range(self, company, owner, person):
        # ~30 years old
        person.date_of_birth = date(1996, 1, 1)
        person.save(update_fields=["date_of_birth"])
        survey = SurveyFactory(
            company=company,
            created_by=owner,
            visibility=Survey.Visibility.PUBLIC,
            targeting={"min_age": 18, "max_age": 25},
        )
        ok, reason = can_access_survey(person, survey)
        assert ok is False

    def test_gender_targeting(self, company, owner, person):
        person.gender = "female"
        person.save(update_fields=["gender"])
        survey = SurveyFactory(
            company=company,
            created_by=owner,
            visibility=Survey.Visibility.PUBLIC,
            targeting={"genders": ["male"]},
        )
        ok, reason = can_access_survey(person, survey)
        assert ok is False

    def test_min_reputation_level_blocks_low_level(self, company, owner, person):
        # person starts at reputation level 1 (registration honor)
        person.honor_points = 10
        person.trust_level = 1
        person.save(update_fields=["honor_points", "trust_level"])
        survey = SurveyFactory(
            company=company,
            created_by=owner,
            visibility=Survey.Visibility.PUBLIC,
            targeting={"min_trust": 3},  # requires Trusted (level 3+)
        )
        ok, reason = can_access_survey(person, survey)
        assert ok is False
        assert "reputation" in reason.lower()

    def test_min_reputation_level_allows_matching(self, company, owner, person):
        person.honor_points = 250
        person.trust_level = 3
        person.save(update_fields=["honor_points", "trust_level"])
        survey = SurveyFactory(
            company=company,
            created_by=owner,
            visibility=Survey.Visibility.PUBLIC,
            targeting={"min_trust": 3},
        )
        ok, reason = can_access_survey(person, survey)
        assert ok is True
        assert reason == ""


@pytest.mark.django_db
class TestDiscoverVisibility:
    def test_private_never_in_discover(self, company, owner, person):
        survey = SurveyFactory(
            company=company,
            created_by=owner,
            visibility=Survey.Visibility.PRIVATE,
            targeting={},
        )
        assert survey_visible_in_discover(survey, person) is False
        assert survey_visible_in_discover(survey, None) is False

    def test_public_no_members_only_visible_to_all(self, company, owner):
        survey = SurveyFactory(
            company=company,
            created_by=owner,
            visibility=Survey.Visibility.PUBLIC,
            targeting={},
        )
        assert survey_visible_in_discover(survey, None) is True

    def test_members_only_hidden_from_non_member(self, company, owner, person):
        survey = SurveyFactory(
            company=company,
            created_by=owner,
            visibility=Survey.Visibility.PUBLIC,
            targeting={"members_only": True},
        )
        assert survey_visible_in_discover(survey, person) is False
        assert survey_visible_in_discover(survey, None) is False

    def test_members_only_visible_to_member(
        self, company, owner, participant, participant_membership
    ):
        survey = SurveyFactory(
            company=company,
            created_by=owner,
            visibility=Survey.Visibility.PUBLIC,
            targeting={"members_only": True},
        )
        assert survey_visible_in_discover(survey, participant) is True
