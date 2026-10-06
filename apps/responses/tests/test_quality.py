"""Tests for survey response quality scoring v1."""
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.accounts.models import HonorEvent
from apps.factories import (
    AnswerFactory,
    QuestionFactory,
    ResponseFactory,
    SurveyFactory,
    UserFactory,
)
from apps.responses.models import QualityAssessment, Response
from apps.responses.quality import (
    compute_quality_score,
    assess_and_reward_response,
    expected_min_seconds,
)
from apps.responses.services import complete_response
from apps.surveys.models import Question, Survey


@pytest.mark.django_db
class TestComputeQualityScore:
    def test_careful_completion_is_high_or_standard(self, company, owner):
        survey = SurveyFactory(company=company, created_by=owner, status=Survey.Status.ACTIVE)
        q1 = QuestionFactory(
            survey=survey,
            order=1,
            type=Question.Type.SINGLE_CHOICE,
            text="Color?",
            config={"choices": ["red", "blue", "green"]},
        )
        q2 = QuestionFactory(
            survey=survey,
            order=2,
            type=Question.Type.TEXT,
            text="Why?",
            is_required=True,
        )
        q3 = QuestionFactory(
            survey=survey,
            order=3,
            type=Question.Type.RATING,
            text="Rate",
            config={"max": 5},
        )
        answers = {
            q1.id: "blue",
            q2.id: "I prefer blue because it feels calmer in the interface.",
            q3.id: 4,
        }
        started = timezone.now() - timedelta(seconds=90)
        completed = timezone.now()
        result = compute_quality_score(
            questions=list(survey.questions.all()),
            answers_map=answers,
            started_at=started,
            completed_at=completed,
        )
        assert result.score >= 50
        assert result.tier in {"standard", "high"}
        assert "speed" not in result.flags

    def test_rushed_straight_line_is_penalized(self, company, owner):
        survey = SurveyFactory(company=company, created_by=owner, status=Survey.Status.ACTIVE)
        questions = []
        for i in range(5):
            questions.append(
                QuestionFactory(
                    survey=survey,
                    order=i + 1,
                    type=Question.Type.RATING,
                    text=f"R{i}",
                    config={"max": 5},
                )
            )
        answers = {q.id: 3 for q in questions}
        started = timezone.now() - timedelta(seconds=3)
        completed = timezone.now()
        result = compute_quality_score(
            questions=questions,
            answers_map=answers,
            started_at=started,
            completed_at=completed,
        )
        assert "speed" in result.flags or "straight_line" in result.flags
        assert result.score < 80

    def test_trivial_text_flagged(self, company, owner):
        survey = SurveyFactory(company=company, created_by=owner)
        q = QuestionFactory(survey=survey, type=Question.Type.TEXT, text="Comments")
        result = compute_quality_score(
            questions=[q],
            answers_map={q.id: "asdf"},
            started_at=timezone.now() - timedelta(seconds=30),
            completed_at=timezone.now(),
        )
        assert "trivial_text" in result.flags or result.components["substance"] < 0.5


@pytest.mark.django_db
class TestAssessAndReward:
    def test_complete_response_creates_assessment_and_honor(self, company, owner):
        user = UserFactory()
        user.refresh_from_db()
        # Bump past pure newcomer soft factor edge by setting level still 1 is ok
        honor_before = user.honor_points

        survey = SurveyFactory(company=company, created_by=owner, status=Survey.Status.ACTIVE)
        q = QuestionFactory(
            survey=survey,
            type=Question.Type.SINGLE_CHOICE,
            config={"choices": ["a", "b"]},
            text="Q?",
        )
        response = ResponseFactory(
            survey=survey,
            participant=user,
            status=Response.Status.IN_PROGRESS,
        )
        # Backdate start so pace is reasonable
        Response.objects.filter(pk=response.pk).update(
            started_at=timezone.now() - timedelta(seconds=45)
        )
        response.refresh_from_db()
        AnswerFactory(response=response, question=q, value="a")

        complete_response(response=response)
        response.refresh_from_db()
        assert response.status == Response.Status.COMPLETED

        qa = QualityAssessment.objects.get(response=response)
        assert qa.score >= 0
        assert qa.tier in {"reject", "low", "standard", "high"}

        user.refresh_from_db()
        if qa.honor_granted:
            assert user.honor_points >= honor_before + qa.honor_granted
            assert HonorEvent.objects.filter(
                user=user, reason=HonorEvent.Reason.SURVEY_QUALITY
            ).exists()

    def test_idempotent_assessment(self, company, owner):
        user = UserFactory()
        survey = SurveyFactory(company=company, created_by=owner, status=Survey.Status.ACTIVE)
        q = QuestionFactory(
            survey=survey,
            type=Question.Type.YES_NO,
            text="Ok?",
        )
        response = ResponseFactory(
            survey=survey,
            participant=user,
            status=Response.Status.IN_PROGRESS,
        )
        Response.objects.filter(pk=response.pk).update(
            started_at=timezone.now() - timedelta(seconds=20)
        )
        response.refresh_from_db()
        AnswerFactory(response=response, question=q, value="yes")
        complete_response(response=response)
        assert QualityAssessment.objects.filter(response=response).count() == 1
        assess_and_reward_response(response)
        assert QualityAssessment.objects.filter(response=response).count() == 1

    def test_expected_min_scales_with_questions(self, company, owner):
        survey = SurveyFactory(company=company, created_by=owner)
        qs = [
            QuestionFactory(survey=survey, order=i, type=Question.Type.YES_NO, text=f"Q{i}")
            for i in range(5)
        ]
        assert expected_min_seconds(qs) >= expected_min_seconds(qs[:1])
