"""Tests for survey publish, freeze, and editability rules."""
import pytest
from django.utils import timezone

from apps.factories import QuestionFactory, SurveyFactory, UserFactory
from apps.surveys.models import Survey
from apps.surveys.services import freeze_survey, publish_survey, reorder_questions


@pytest.mark.django_db
class TestPublishSurvey:
    def test_publish_draft_with_questions(self, draft_survey):
        result = publish_survey(draft_survey)
        assert result.status == Survey.Status.ACTIVE
        assert result.pk == draft_survey.pk

    def test_publish_is_idempotent_when_already_active(self, draft_survey):
        publish_survey(draft_survey)
        draft_survey.refresh_from_db()
        # Second call must not raise
        result = publish_survey(draft_survey)
        assert result.status == Survey.Status.ACTIVE

    def test_cannot_publish_paused_survey(self, draft_survey):
        draft_survey.status = Survey.Status.PAUSED
        draft_survey.save(update_fields=["status"])
        with pytest.raises(ValueError, match="Only draft"):
            publish_survey(draft_survey)

    def test_cannot_publish_closed_survey(self, draft_survey):
        draft_survey.status = Survey.Status.CLOSED
        draft_survey.save(update_fields=["status"])
        with pytest.raises(ValueError, match="Only draft"):
            publish_survey(draft_survey)

    def test_cannot_publish_without_questions(self, company, owner):
        empty = SurveyFactory(company=company, created_by=owner, status=Survey.Status.DRAFT)
        with pytest.raises(ValueError, match="no questions"):
            publish_survey(empty)

    def test_cannot_publish_deleted_survey(self, draft_survey):
        draft_survey.is_deleted = True
        draft_survey.save(update_fields=["is_deleted"])
        with pytest.raises(ValueError, match="deleted"):
            publish_survey(draft_survey)

    def test_free_survey_publish_forces_public_and_clears_targeting(self, draft_survey):
        draft_survey.is_paid = False
        draft_survey.visibility = Survey.Visibility.PRIVATE
        draft_survey.targeting = {"members_only": True, "min_level": 5}
        draft_survey.points_reward = 99  # should be zeroed
        draft_survey.save()
        publish_survey(draft_survey)
        draft_survey.refresh_from_db()
        assert draft_survey.visibility == Survey.Visibility.PUBLIC
        assert draft_survey.targeting == {}
        assert draft_survey.points_reward == 0
        assert draft_survey.status == Survey.Status.ACTIVE

    def test_paid_survey_publish_keeps_points_and_visibility(self, paid_draft_survey):
        paid_draft_survey.visibility = Survey.Visibility.PRIVATE
        paid_draft_survey.targeting = {"members_only": True}
        paid_draft_survey.save()
        publish_survey(paid_draft_survey)
        paid_draft_survey.refresh_from_db()
        assert paid_draft_survey.status == Survey.Status.ACTIVE
        assert paid_draft_survey.is_paid is True
        assert paid_draft_survey.points_reward == 50
        assert paid_draft_survey.visibility == Survey.Visibility.PRIVATE
        assert paid_draft_survey.targeting.get("members_only") is True


@pytest.mark.django_db
class TestFreezeSurvey:
    def test_freeze_sets_flags(self, draft_survey):
        before = timezone.now()
        freeze_survey(draft_survey)
        draft_survey.refresh_from_db()
        assert draft_survey.is_frozen is True
        assert draft_survey.frozen_at is not None
        assert draft_survey.frozen_at >= before

    def test_freeze_is_idempotent(self, draft_survey):
        freeze_survey(draft_survey)
        draft_survey.refresh_from_db()
        first_at = draft_survey.frozen_at
        freeze_survey(draft_survey)
        draft_survey.refresh_from_db()
        assert draft_survey.frozen_at == first_at


@pytest.mark.django_db
class TestIsEditable:
    def test_draft_not_frozen_is_editable(self, draft_survey):
        assert draft_survey.is_editable is True

    def test_frozen_draft_not_editable(self, draft_survey):
        freeze_survey(draft_survey)
        draft_survey.refresh_from_db()
        assert draft_survey.is_editable is False

    def test_active_not_editable(self, draft_survey):
        publish_survey(draft_survey)
        draft_survey.refresh_from_db()
        assert draft_survey.is_editable is False

    def test_reorder_blocked_when_not_editable(self, draft_survey):
        q = draft_survey.questions.first()
        publish_survey(draft_survey)
        draft_survey.refresh_from_db()
        with pytest.raises(ValueError, match="frozen|non-draft"):
            reorder_questions(draft_survey, [q.id])
