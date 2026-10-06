"""Shared pytest fixtures for SURVERA apps."""
import pytest
from django.test import RequestFactory

from apps.factories import (
    CompanyFactory,
    CompanyMembershipFactory,
    QuestionFactory,
    SurveyFactory,
    UserFactory,
)
from apps.companies.models import CompanyMembership


@pytest.fixture
def rf():
    return RequestFactory()


@pytest.fixture
def person(db):
    return UserFactory(user_type="person")


@pytest.fixture
def owner(db):
    return UserFactory(user_type="company_member")


@pytest.fixture
def company(db):
    return CompanyFactory()


@pytest.fixture
def owner_membership(db, company, owner):
    return CompanyMembershipFactory(
        company=company,
        user=owner,
        role=CompanyMembership.Role.OWNER,
        is_active=True,
    )


@pytest.fixture
def moderator(db):
    return UserFactory(user_type="company_member")


@pytest.fixture
def moderator_membership(db, company, moderator):
    return CompanyMembershipFactory(
        company=company,
        user=moderator,
        role=CompanyMembership.Role.MODERATOR,
        is_active=True,
    )


@pytest.fixture
def participant(db):
    return UserFactory(user_type="person")


@pytest.fixture
def participant_membership(db, company, participant):
    return CompanyMembershipFactory(
        company=company,
        user=participant,
        role=CompanyMembership.Role.PARTICIPANT,
        is_active=True,
    )


@pytest.fixture
def draft_survey(db, company, owner):
    survey = SurveyFactory(
        company=company,
        created_by=owner,
        status="draft",
        is_paid=False,
        points_reward=0,
        visibility="public",
    )
    QuestionFactory(survey=survey, order=1, text="Q1?", is_required=True)
    return survey


@pytest.fixture
def paid_draft_survey(db, company, owner):
    survey = SurveyFactory(
        company=company,
        created_by=owner,
        status="draft",
        is_paid=True,
        points_reward=50,
        visibility="public",
    )
    QuestionFactory(survey=survey, order=1, text="Q1?", is_required=True)
    return survey
