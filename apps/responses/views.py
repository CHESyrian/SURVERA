"""Participant-facing take-survey flow + company CSV export."""
import logging

logger = logging.getLogger(__name__)

import csv
import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_http_methods

from apps.accounts.decorators import email_verified_required, user_email_verified
from apps.companies.models import CompanyMembership
from apps.surveys.conditions import conditions_payload
from apps.surveys.models import Question, Survey
from apps.surveys.targeting import can_access_survey

from .models import Response
from .services import complete_response, save_answers, start_response
from .validation import validate_all_answers


def _parse_answer_value(question: Question, post_data, key_prefix: str):
    key = f"{key_prefix}{question.id}"
    qtype = question.type
    if qtype == Question.Type.MULTIPLE_CHOICE:
        return post_data.getlist(key)
    if qtype == Question.Type.RANKING:
        vals = post_data.getlist(key)
        if vals:
            return vals
        raw = post_data.get(key, "").strip()
        if raw.startswith("["):
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return []
        return []
    if qtype == Question.Type.MATRIX:
        rows = (question.config or {}).get("rows") or []
        result = {}
        for row in rows:
            cell = post_data.get(f"{key}__{row}", "").strip()
            if cell:
                result[row] = cell
        return result
    if qtype in {Question.Type.RATING, Question.Type.SCALE, Question.Type.NUMBER}:
        raw = post_data.get(key, "").strip()
        if raw == "":
            return None
        try:
            if qtype == Question.Type.NUMBER and "." in raw:
                return float(raw)
            return int(raw)
        except ValueError:
            return raw
    return post_data.get(key, "").strip()


def _take_context(survey, questions, errors=None, posted=None):
    errors = errors or {}
    posted = posted or {}
    posted_clean = {}
    for qid, val in posted.items():
        try:
            posted_clean[int(qid)] = val
        except (TypeError, ValueError):
            continue
    return {
        "survey": survey,
        "questions": questions,
        "errors": errors,
        "posted": posted,
        "errors_json": json.dumps({str(k): str(v) for k, v in errors.items()}),
        "posted_json": json.dumps(posted_clean, default=str),
        "conditions_json": json.dumps(conditions_payload(questions)),
    }


@require_http_methods(["GET", "POST"])
def take_survey(request, pk):
    survey = get_object_or_404(
        Survey.objects.prefetch_related("questions"), pk=pk, is_deleted=False
    )
    if not survey.can_accept_responses():
        return render(request, "responses/closed.html", {"survey": survey})

    # Taking a survey requires a verified account (no anonymous participation).
    if not request.user.is_authenticated:
        messages.info(request, _("Please log in to take this survey."))
        return redirect(f"{reverse('accounts:login')}?next={request.path}")
    if not user_email_verified(request.user):
        messages.warning(
            request,
            _("Please verify your email before taking surveys."),
        )
        return redirect(f"{reverse('accounts:verify_email')}?next={request.path}")

    user = request.user

    allowed, reason = can_access_survey(user, survey)
    if not allowed:
        messages.error(request, reason)
        return redirect("surveys:discover")

    if user:
        existing = Response.objects.filter(
            survey=survey, participant=user, status=Response.Status.COMPLETED
        ).first()
        if existing:
            return render(request, "responses/already_done.html", {"survey": survey})

    questions = list(survey.questions.all())

    if request.method == "POST":
        raw_answers = {q.id: _parse_answer_value(q, request.POST, "q_") for q in questions}
        normalized, errors = validate_all_answers(questions, raw_answers)
        if errors:
            return render(
                request,
                "responses/take.html",
                _take_context(survey, questions, errors=errors, posted=raw_answers),
            )
        try:
            response = start_response(survey=survey, user=user, request=request)
        except ValueError as e:
            messages.error(request, str(e))
            return redirect("responses:take", pk=survey.pk)
        save_answers(response=response, answers_data=normalized)
        try:
            complete_response(response=response)
        except ValueError as e:
            messages.error(request, str(e))
            return redirect("responses:take", pk=survey.pk)

        msg = str(_("Thank you! Your responses have been recorded."))
        extras = []
        if user and survey.points_reward:
            extras.append(f"+{survey.points_reward} points")
        if user:
            try:
                from apps.rewards.levels import XP_SURVEY_COMPLETION
                extras.append(f"+{XP_SURVEY_COMPLETION} XP")
            except Exception:
                logger.exception("Side-effect failed in responses view")
        if extras:
            msg = f"{msg} ({', '.join(extras)})"
        messages.success(request, msg)
        return redirect("responses:thanks", pk=survey.pk)

    return render(request, "responses/take.html", _take_context(survey, questions))


def thanks(request, pk):
    survey = get_object_or_404(Survey, pk=pk, is_deleted=False)
    return render(request, "responses/thanks.html", {"survey": survey})


def _can_view_survey_results(user, survey: Survey) -> bool:
    if user.is_superuser:
        return True
    if not survey.company_id:
        return False
    membership = CompanyMembership.objects.filter(
        company_id=survey.company_id, user=user, is_active=True
    ).first()
    return bool(membership and membership.can_manage_surveys)


@email_verified_required
def export_csv(request, pk):
    """
    Export completed responses as CSV.

    Privacy: does not include participant personal data (email, name, user id).
    Rows are identified only by anonymous response_id + completed_at + answers.
    """
    from .services import format_answer_value

    survey = get_object_or_404(Survey, pk=pk, is_deleted=False)
    if not _can_view_survey_results(request.user, survey):
        raise PermissionDenied
    questions = list(survey.questions.order_by("order", "id"))
    responses = (
        Response.objects.filter(survey=survey, status=Response.Status.COMPLETED)
        .prefetch_related("answers")
        .order_by("completed_at")
    )
    http_response = HttpResponse(content_type="text/csv")
    http_response["Content-Disposition"] = f'attachment; filename="survey_{survey.pk}_responses.csv"'
    writer = csv.writer(http_response)
    # No participant PII columns (email, name, user id, IP, user-agent).
    header = ["response_id", "completed_at"] + [f"q{q.id}_{q.type}" for q in questions]
    writer.writerow(header)
    for resp in responses:
        answers_map = {a.question_id: a.value for a in resp.answers.all()}
        row = [
            resp.pk,
            resp.completed_at.isoformat() if resp.completed_at else "",
        ]
        for q in questions:
            val = answers_map.get(q.id, "")
            row.append(format_answer_value(val) if val != "" else "")
        writer.writerow(row)
    return http_response


@login_required
def response_list(request, pk):
    survey = get_object_or_404(Survey, pk=pk, is_deleted=False)
    if not _can_view_survey_results(request.user, survey):
        raise PermissionDenied
    responses = (
        Response.objects.filter(survey=survey)
        .select_related("participant")
        .order_by("-started_at")[:200]
    )
    completed_count = Response.objects.filter(
        survey=survey, status=Response.Status.COMPLETED
    ).count()
    return render(
        request,
        "responses/list.html",
        {"survey": survey, "responses": responses, "completed_count": completed_count},
    )


@login_required
def response_detail(request, pk):
    """Show one response with questions and answers (managers only)."""
    from .services import build_response_answer_rows

    response_obj = get_object_or_404(
        Response.objects.select_related("survey", "survey__company", "participant"),
        pk=pk,
    )
    survey = response_obj.survey
    if survey.is_deleted:
        raise PermissionDenied
    if not _can_view_survey_results(request.user, survey):
        raise PermissionDenied

    rows = build_response_answer_rows(response_obj)
    return render(
        request,
        "responses/detail.html",
        {
            "survey": survey,
            "response_obj": response_obj,
            "answer_rows": rows,
        },
    )



@login_required
@require_http_methods(["GET", "POST"])
def report_response(request, pk):
    """Company manager reports a participant response."""
    from apps.companies.services import user_can_manage_surveys
    from apps.responses.forms import ReportForm
    from apps.responses.models import Report

    response_obj = get_object_or_404(
        Response.objects.select_related("survey", "survey__company", "participant"),
        pk=pk,
    )
    survey = response_obj.survey
    if not survey.company_id:
        raise PermissionDenied
    if not request.user.is_superuser and not user_can_manage_surveys(request.user, survey.company):
        raise PermissionDenied

    if request.method == "POST":
        form = ReportForm(request.POST)
        if form.is_valid():
            report = form.save(commit=False)
            report.reporter = request.user
            report.company = survey.company
            report.survey = survey
            report.response = response_obj
            report.reported_user = response_obj.participant
            report.status = Report.Status.PENDING
            report.save()
            messages.success(request, _("Report submitted. Staff will review it."))
            return redirect("responses:list", pk=survey.pk)
    else:
        form = ReportForm()

    return render(
        request,
        "responses/report.html",
        {
            "form": form,
            "response_obj": response_obj,
            "survey": survey,
        },
    )
