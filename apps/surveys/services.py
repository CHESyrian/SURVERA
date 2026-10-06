"""Survey application services."""
from __future__ import annotations

import logging

from django.db import transaction
from django.utils import timezone

from .models import Question, Survey

logger = logging.getLogger(__name__)


@transaction.atomic
def freeze_survey(survey: Survey) -> Survey:
    if survey.is_frozen:
        return survey
    survey.is_frozen = True
    survey.frozen_at = timezone.now()
    survey.save(update_fields=["is_frozen", "frozen_at", "updated_at"])
    return survey


@transaction.atomic
def publish_survey(survey: Survey) -> Survey:
    if survey.is_deleted:
        raise ValueError("Cannot publish a deleted survey.")
    if survey.status == Survey.Status.ACTIVE:
        return survey
    if survey.status != Survey.Status.DRAFT:
        raise ValueError("Only draft surveys can be published.")
    if not survey.questions.exists():
        raise ValueError("Cannot publish a survey with no questions.")
    if not survey.company_id:
        raise ValueError("Survey must belong to a company.")

    # Free surveys are always public and discoverable.
    if not survey.is_paid:
        survey.visibility = Survey.Visibility.PUBLIC
        survey.targeting = {}
        survey.points_reward = 0
        survey.response_target = None

    survey.status = Survey.Status.ACTIVE
    survey.save(
        update_fields=[
            "status",
            "visibility",
            "targeting",
            "points_reward",
            "response_target",
            "updated_at",
        ]
    )
    # Side effect: notifications must not roll back publish.
    try:
        from apps.notifications.services import queue_survey_published_notifications

        queue_survey_published_notifications(survey)
    except Exception:
        logger.exception(
            "Failed to queue publish notifications for survey_id=%s",
            survey.pk,
        )
    return survey


def reorder_questions(survey: Survey, ordered_question_ids: list[int]) -> None:
    if not survey.is_editable:
        raise ValueError("Cannot reorder questions on a frozen or non-draft survey.")
    id_to_order = {qid: idx for idx, qid in enumerate(ordered_question_ids)}
    questions = list(survey.questions.filter(id__in=ordered_question_ids))
    for q in questions:
        q.order = id_to_order[q.id]
    Question.objects.bulk_update(questions, ["order"])
