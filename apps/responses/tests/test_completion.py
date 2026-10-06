"""Tests for response completion: freeze, points-only-on-paid, XP."""
from types import SimpleNamespace

import pytest

from apps.factories import (
    QuestionFactory,
    ResponseFactory,
    SurveyFactory,
    UserFactory,
)
from apps.responses.models import Answer, Response
from apps.responses.services import complete_response, start_response
from apps.rewards.models import PointsTransaction, XPTransaction
from apps.rewards.services import get_points_balance
from apps.surveys.models import Survey
from apps.surveys.services import publish_survey


def _fake_request(ip="127.0.0.1", ua="test-agent"):
    return SimpleNamespace(
        META={
            "REMOTE_ADDR": ip,
            "HTTP_USER_AGENT": ua,
            "HTTP_X_FORWARDED_FOR": "",
        }
    )


@pytest.mark.django_db
class TestPointsOnlyOnPaid:
    def _complete_with_answer(self, survey, user):
        publish_survey(survey)
        survey.refresh_from_db()
        q = survey.questions.first()
        response = Response.objects.create(
            survey=survey,
            participant=user,
            status=Response.Status.IN_PROGRESS,
        )
        Answer.objects.create(response=response, question=q, value="yes")
        return complete_response(response=response)

    def test_paid_survey_with_points_awards_points(self, paid_draft_survey, person):
        result = self._complete_with_answer(paid_draft_survey, person)
        assert result.status == Response.Status.COMPLETED
        assert get_points_balance(person) == 50
        assert PointsTransaction.objects.filter(
            user=person, response=result, reason=PointsTransaction.Reason.SURVEY_COMPLETION
        ).exists()

    def test_free_survey_awards_no_points(self, draft_survey, person):
        result = self._complete_with_answer(draft_survey, person)
        assert result.status == Response.Status.COMPLETED
        assert get_points_balance(person) == 0
        assert not PointsTransaction.objects.filter(user=person).exists()

    def test_paid_survey_with_zero_points_awards_no_points(self, company, owner, person):
        survey = SurveyFactory(
            company=company,
            created_by=owner,
            status=Survey.Status.DRAFT,
            is_paid=True,
            points_reward=0,
        )
        QuestionFactory(survey=survey, order=1, text="Q?", is_required=True)
        result = self._complete_with_answer(survey, person)
        assert result.status == Response.Status.COMPLETED
        assert get_points_balance(person) == 0

    def test_points_idempotent_on_double_complete(self, paid_draft_survey, person):
        result = self._complete_with_answer(paid_draft_survey, person)
        # complete again (service is idempotent for COMPLETED)
        complete_response(response=result)
        assert PointsTransaction.objects.filter(
            user=person, response=result, reason=PointsTransaction.Reason.SURVEY_COMPLETION
        ).count() == 1
        assert get_points_balance(person) == 50


@pytest.mark.django_db
class TestXPOnCompletion:
    def test_completion_awards_xp_for_free_survey(self, draft_survey, person):
        publish_survey(draft_survey)
        q = draft_survey.questions.first()
        response = Response.objects.create(
            survey=draft_survey, participant=person, status=Response.Status.IN_PROGRESS
        )
        Answer.objects.create(response=response, question=q, value="answer")
        complete_response(response=response)
        assert XPTransaction.objects.filter(
            user=person, response=response, reason=XPTransaction.Reason.SURVEY_COMPLETION
        ).exists()

    def test_completion_awards_xp_for_paid_survey(self, paid_draft_survey, person):
        publish_survey(paid_draft_survey)
        q = paid_draft_survey.questions.first()
        response = Response.objects.create(
            survey=paid_draft_survey, participant=person, status=Response.Status.IN_PROGRESS
        )
        Answer.objects.create(response=response, question=q, value="answer")
        complete_response(response=response)
        assert XPTransaction.objects.filter(
            user=person, response=response, reason=XPTransaction.Reason.SURVEY_COMPLETION
        ).exists()


@pytest.mark.django_db
class TestFreezeOnFirstResponse:
    def test_first_completion_freezes_survey(self, draft_survey, person):
        publish_survey(draft_survey)
        draft_survey.refresh_from_db()
        assert draft_survey.is_frozen is False
        q = draft_survey.questions.first()
        response = Response.objects.create(
            survey=draft_survey, participant=person, status=Response.Status.IN_PROGRESS
        )
        Answer.objects.create(response=response, question=q, value="yes")
        complete_response(response=response)
        draft_survey.refresh_from_db()
        assert draft_survey.is_frozen is True
        assert draft_survey.frozen_at is not None
        assert draft_survey.is_editable is False

    def test_second_response_does_not_unfreeze(self, draft_survey, person):
        publish_survey(draft_survey)
        q = draft_survey.questions.first()
        r1 = Response.objects.create(
            survey=draft_survey, participant=person, status=Response.Status.IN_PROGRESS
        )
        Answer.objects.create(response=r1, question=q, value="yes")
        complete_response(response=r1)
        draft_survey.refresh_from_db()
        frozen_at = draft_survey.frozen_at

        other = UserFactory()
        r2 = Response.objects.create(
            survey=draft_survey, participant=other, status=Response.Status.IN_PROGRESS
        )
        Answer.objects.create(response=r2, question=q, value="no")
        complete_response(response=r2)
        draft_survey.refresh_from_db()
        assert draft_survey.is_frozen is True
        assert draft_survey.frozen_at == frozen_at


@pytest.mark.django_db
class TestStartResponse:
    def test_start_on_active_survey(self, draft_survey, person):
        publish_survey(draft_survey)
        req = _fake_request()
        response = start_response(survey=draft_survey, user=person, request=req)
        assert response.status == Response.Status.IN_PROGRESS
        assert response.participant_id == person.pk

    def test_cannot_start_on_draft(self, draft_survey, person):
        req = _fake_request()
        with pytest.raises(ValueError, match="not accepting"):
            start_response(survey=draft_survey, user=person, request=req)

    def test_cannot_restart_completed(self, draft_survey, person):
        publish_survey(draft_survey)
        q = draft_survey.questions.first()
        r = Response.objects.create(
            survey=draft_survey, participant=person, status=Response.Status.IN_PROGRESS
        )
        Answer.objects.create(response=r, question=q, value="yes")
        complete_response(response=r)
        req = _fake_request()
        with pytest.raises(ValueError, match="already completed"):
            start_response(survey=draft_survey, user=person, request=req)

    def test_missing_required_blocks_complete(self, draft_survey, person):
        publish_survey(draft_survey)
        response = Response.objects.create(
            survey=draft_survey, participant=person, status=Response.Status.IN_PROGRESS
        )
        # no answers
        with pytest.raises(ValueError, match="required"):
            complete_response(response=response)
