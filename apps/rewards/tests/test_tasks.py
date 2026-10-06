"""Daily/weekly task progress and rewards."""
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
from apps.responses.models import Response
from apps.responses.services import complete_response
from apps.rewards.models import TaskDefinition, TaskProgress, XPTransaction
from apps.rewards.tasks_service import (
    DAILY_CODE,
    ensure_default_task_definitions,
    list_user_tasks,
    on_survey_completed,
)
from apps.surveys.models import Question, Survey


def _complete_one(user, company, owner):
    survey = SurveyFactory(company=company, created_by=owner, status=Survey.Status.ACTIVE)
    q = QuestionFactory(
        survey=survey, type=Question.Type.YES_NO, text="Ok?", is_required=True
    )
    response = ResponseFactory(
        survey=survey, participant=user, status=Response.Status.IN_PROGRESS
    )
    Response.objects.filter(pk=response.pk).update(
        started_at=timezone.now() - timezone.timedelta(seconds=30)
    )
    response.refresh_from_db()
    AnswerFactory(response=response, question=q, value="yes")
    complete_response(response=response)
    return response


@pytest.mark.django_db
class TestTasks:
    def test_definitions_seeded(self):
        ensure_default_task_definitions()
        assert TaskDefinition.objects.filter(code=DAILY_CODE).exists()

    def test_daily_completes_after_three(self, company, owner):
        user = UserFactory()
        user.refresh_from_db()
        honor0 = user.honor_points
        for _ in range(3):
            _complete_one(user, company, owner)
        ensure_default_task_definitions()
        daily = TaskDefinition.objects.get(code=DAILY_CODE)
        progress = TaskProgress.objects.filter(user=user, definition=daily).first()
        assert progress is not None
        assert progress.current_count >= 3
        assert progress.completed_at is not None
        user.refresh_from_db()
        assert user.honor_points >= honor0 + 5
        assert XPTransaction.objects.filter(
            user=user, reason=XPTransaction.Reason.TASK_DAILY
        ).exists()

    def test_list_user_tasks(self):
        user = UserFactory()
        data = list_user_tasks(user)
        assert len(data["daily"]) >= 1
        assert len(data["weekly"]) >= 1
