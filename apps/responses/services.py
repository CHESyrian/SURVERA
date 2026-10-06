"""Participation lifecycle: start, save answers, complete."""

import logging

logger = logging.getLogger(__name__)

from django.db import transaction
from django.utils import timezone

from apps.rewards.services import award_points_for_response, award_xp_for_survey_completion
from apps.surveys.services import freeze_survey

from .models import Answer, Response


def _client_meta(request):
    ip = request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip() or request.META.get(
        "REMOTE_ADDR"
    )
    ua = (request.META.get("HTTP_USER_AGENT") or "")[:400]
    return ip, ua


@transaction.atomic
def start_response(*, survey, user, request) -> Response:
    if not survey.can_accept_responses():
        raise ValueError("This survey is not accepting responses.")

    if user and user.is_authenticated:
        existing = (
            Response.objects.select_for_update()
            .filter(survey=survey, participant=user)
            .first()
        )
        if existing:
            if existing.status == Response.Status.COMPLETED:
                raise ValueError("You have already completed this survey.")
            return existing
        participant = user
    else:
        if not survey.allow_anonymous:
            raise ValueError("This survey requires login.")
        participant = None

    ip, ua = _client_meta(request)
    return Response.objects.create(
        survey=survey,
        participant=participant,
        status=Response.Status.IN_PROGRESS,
        ip_address=ip,
        user_agent=ua,
    )


@transaction.atomic
def save_answers(*, response: Response, answers_data: dict) -> Response:
    if response.status == Response.Status.COMPLETED:
        raise ValueError("Cannot modify a completed response.")
    survey = response.survey
    questions = {q.id: q for q in survey.questions.all()}
    for qid, value in answers_data.items():
        qid = int(qid)
        if qid not in questions:
            continue
        Answer.objects.update_or_create(
            response=response, question_id=qid, defaults={"value": value}
        )
    return response


@transaction.atomic
def complete_response(*, response: Response) -> Response:
    if response.status == Response.Status.COMPLETED:
        return response

    survey = response.survey
    from apps.surveys.conditions import visible_questions

    answers_map = {a.question_id: a.value for a in response.answers.all()}
    questions = list(survey.questions.all())
    visible = visible_questions(questions, answers_map)
    required_ids = {q.id for q in visible if q.is_required}
    answered_ids = set(answers_map.keys())
    missing = required_ids - answered_ids
    if missing:
        raise ValueError("Please answer all required questions.")

    response.status = Response.Status.COMPLETED
    response.completed_at = timezone.now()
    response.save(update_fields=["status", "completed_at", "updated_at"])

    if not survey.is_frozen:
        freeze_survey(survey)

    if response.participant_id:
        if survey.is_paid and survey.points_reward > 0:
            award_points_for_response(
                user=response.participant,
                response=response,
                amount=survey.points_reward,
            )
            try:
                from apps.notifications.services import notify_points_awarded

                notify_points_awarded(
                    user=response.participant,
                    amount=survey.points_reward,
                    survey_title=survey.title,
                    response_id=response.pk,
                )
            except Exception:
                logger.exception(
                    "Failed to notify points awarded user_id=%s response_id=%s amount=%s",
                    response.participant_id,
                    response.pk,
                    survey.points_reward,
                )
        award_xp_for_survey_completion(user=response.participant, response=response)
        try:
            from apps.rewards.tasks_service import on_survey_completed

            on_survey_completed(user=response.participant, response=response)
        except Exception:
            logger.exception(
                "Task progress update failed response_id=%s",
                response.pk,
            )

    # Quality score + optional honor (best-effort; never fails completion)
    try:
        from apps.responses.quality import assess_and_reward_response

        assess_and_reward_response(response)
    except Exception:
        logger.exception(
            "Quality assessment failed response_id=%s",
            response.pk,
        )

    return response


def format_answer_value(value, question=None) -> str:
    """Human-readable string for an Answer.value (JSON).

    For rating questions, returns a star string (e.g. ★★★☆☆) when possible.
    """
    if value is None:
        return ""
    if question is not None and getattr(question, "type", None) == "rating":
        try:
            n = int(float(value))
            max_r = 5
            if isinstance(getattr(question, "config", None), dict):
                max_r = int(question.config.get("max") or 5)
            max_r = max(1, min(max_r, 10))
            n = max(0, min(n, max_r))
            return "★" * n + "☆" * (max_r - n)
        except (TypeError, ValueError):
            pass
    if isinstance(value, list):
        return " | ".join(str(v) for v in value)
    if isinstance(value, dict):
        return "; ".join(f"{k}: {v}" for k, v in value.items())
    return str(value)


def build_response_answer_rows(response: Response) -> list[dict]:
    """
    Ordered list of {question, answer, display_value} for a response.
    Includes every survey question; unanswered ones have answer=None.
    Rating answers are shown as stars.
    """
    questions = list(response.survey.questions.order_by("order", "id"))
    answers_map = {a.question_id: a for a in response.answers.select_related("question")}
    rows = []
    for q in questions:
        ans = answers_map.get(q.id)
        rows.append(
            {
                "question": q,
                "answer": ans,
                "display_value": (
                    format_answer_value(ans.value, question=q) if ans is not None else ""
                ),
            }
        )
    return rows
