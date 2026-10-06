"""Tests for survey analytics service and view access."""
import pytest
from django.urls import reverse
from django.utils import timezone

from apps.factories import (
    AnswerFactory,
    QuestionFactory,
    ResponseFactory,
    SurveyFactory,
    UserFactory,
)
from apps.responses.models import Response
from apps.surveys.analytics import get_survey_analytics
from apps.surveys.models import Question, Survey

BACKEND = "django.contrib.auth.backends.ModelBackend"


def _login(client, user):
    client.force_login(user, backend=BACKEND)


@pytest.mark.django_db
class TestGetSurveyAnalytics:
    def test_empty_survey_stats(self, company, owner):
        survey = SurveyFactory(company=company, created_by=owner)
        QuestionFactory(survey=survey, type=Question.Type.TEXT, text="Open?")
        stats = get_survey_analytics(survey)
        assert stats["total"] == 0
        assert stats["completed"] == 0
        assert stats["completion_rate"] == 0.0
        assert len(stats["daily_completed"]) == 14
        assert stats["question_stats"][0]["answer_count"] == 0

    def test_choice_breakdown(self, company, owner, person):
        survey = SurveyFactory(company=company, created_by=owner, status=Survey.Status.ACTIVE)
        q = QuestionFactory(
            survey=survey,
            type=Question.Type.SINGLE_CHOICE,
            text="Color?",
            config={"choices": ["red", "blue"]},
        )
        r1 = ResponseFactory(
            survey=survey,
            participant=person,
            status=Response.Status.COMPLETED,
            completed_at=timezone.now(),
        )
        AnswerFactory(response=r1, question=q, value="red")
        other = UserFactory()
        r2 = ResponseFactory(
            survey=survey,
            participant=other,
            status=Response.Status.COMPLETED,
            completed_at=timezone.now(),
        )
        AnswerFactory(response=r2, question=q, value="red")

        stats = get_survey_analytics(survey)
        assert stats["completed"] == 2
        assert stats["completion_rate"] == 100.0
        assert stats["status_chart"]["total"] == 2
        bd = stats["question_stats"][0]["breakdown"]
        assert bd["kind"] == "distribution"
        by_label = {i["label"]: i["count"] for i in bd["items"]}
        assert by_label.get("red") == 2
        red_item = next(i for i in bd["items"] if i["label"] == "red")
        assert red_item["percent"] == 100.0
        assert red_item["bar_pct"] >= 4

    def test_target_pct(self, company, owner, person):
        survey = SurveyFactory(
            company=company,
            created_by=owner,
            status=Survey.Status.ACTIVE,
            response_target=10,
            is_paid=True,
            points_reward=5,
        )
        ResponseFactory(
            survey=survey,
            participant=person,
            status=Response.Status.COMPLETED,
            completed_at=timezone.now(),
        )
        stats = get_survey_analytics(survey)
        assert stats["target_pct"] == 10.0


@pytest.mark.django_db
class TestAnalyticsView:
    def test_manager_can_view(self, client, company, owner, owner_membership):
        survey = SurveyFactory(company=company, created_by=owner, status=Survey.Status.ACTIVE)
        _login(client, owner)
        url = reverse("surveys:analytics", kwargs={"pk": survey.pk})
        r = client.get(url)
        assert r.status_code == 200
        assert b"Completion rate" in r.content or b"completion" in r.content.lower()

    def test_stranger_forbidden(self, client, company, owner, owner_membership):
        survey = SurveyFactory(company=company, created_by=owner, status=Survey.Status.ACTIVE)
        stranger = UserFactory()
        _login(client, stranger)
        url = reverse("surveys:analytics", kwargs={"pk": survey.pk})
        assert client.get(url).status_code == 403
