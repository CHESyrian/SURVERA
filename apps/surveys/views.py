"""Survey management views – company-owned surveys only."""
import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_http_methods, require_POST

from apps.accounts.decorators import email_verified_required
from apps.companies.models import Company, CompanyMembership
from apps.common.constants import DISCOVER_PAGE_SIZE, SURVEY_CATEGORY_LABELS

from .forms import QuestionForm, SurveyForm
from .limits import apply_survey_pricing_rules, can_create_survey, user_manageable_companies
from .models import Question, Survey
from .services import publish_survey

logger = logging.getLogger(__name__)


def _user_companies(user):
    return CompanyMembership.objects.filter(user=user, is_active=True).select_related("company")


def _get_membership_for_survey(user, survey: Survey) -> CompanyMembership | None:
    if not survey.company_id:
        return None
    return (
        CompanyMembership.objects.filter(
            user=user, company_id=survey.company_id, is_active=True
        )
        .select_related("company")
        .first()
    )


def _can_edit_survey(user, survey: Survey) -> bool:
    if user.is_superuser:
        return True
    membership = _get_membership_for_survey(user, survey)
    return bool(membership and membership.can_manage_surveys)


def _require_editor(user, survey: Survey) -> None:
    if not _can_edit_survey(user, survey):
        raise PermissionDenied(_("You do not have permission to edit this survey."))


def _resolve_create_company(request, editable_memberships):
    """Pick company for a new survey (non-superuser managers only)."""
    company_id = request.POST.get("company_id") or request.GET.get("company_id")
    if not editable_memberships:
        return None
    if company_id:
        for m in editable_memberships:
            if str(m.company_id) == str(company_id):
                return m.company
    return editable_memberships[0].company


@login_required
def survey_list(request):
    memberships = list(_user_companies(request.user))
    company_ids = [m.company_id for m in memberships]
    if request.user.is_superuser:
        # Platform (SURVERA) surveys + all company surveys
        surveys = Survey.objects.select_related("company").order_by("-created_at")
    else:
        surveys = (
            Survey.objects.filter(company_id__in=company_ids)
            .select_related("company")
            .order_by("-created_at")
        )
    allowed, create_msg = can_create_survey(request.user)
    has_company_editor = bool(user_manageable_companies(request.user)) or request.user.is_superuser
    return render(
        request,
        "surveys/list.html",
        {
            "surveys": surveys,
            "memberships": memberships,
            "can_create": allowed,
            "create_msg": create_msg if not allowed else "",
            "has_company": has_company_editor,
        },
    )


@email_verified_required
@require_http_methods(["GET", "POST"])
def survey_create(request):
    """Create a survey.

    - Superuser → always owned by platform company SURVERA.
    - Company owner/moderator → survey owned by their company.
    """
    allowed, reason = can_create_survey(request.user)
    if not allowed:
        messages.error(request, reason)
        return redirect("surveys:list")

    from apps.companies.services import (
        ensure_superuser_on_platform,
        get_or_create_platform_company,
    )

    is_platform = bool(request.user.is_superuser)
    editable_memberships = user_manageable_companies(request.user)
    company = None
    company_choices = []

    if is_platform:
        company = get_or_create_platform_company()
        ensure_superuser_on_platform(request.user)
    else:
        company = _resolve_create_company(request, editable_memberships)
        if company is None:
            messages.error(
                request,
                _("Create a company first, then you can create surveys."),
            )
            return redirect("companies:create")
        if len(editable_memberships) > 1:
            company_choices = [m.company for m in editable_memberships]

    draft = Survey(
        created_by=request.user,
        status=Survey.Status.DRAFT,
        company=company,
        visibility=Survey.Visibility.PUBLIC,
    )

    if request.method == "POST":
        if is_platform:
            company = get_or_create_platform_company()
        else:
            company = _resolve_create_company(request, editable_memberships) or company
        draft.company = company
        form = SurveyForm(request.POST, instance=draft, free_mode=False, company_mode=True)
        if form.is_valid():
            survey = form.save(commit=False)
            survey.created_by = request.user
            survey.status = Survey.Status.DRAFT
            survey.company = company
            apply_survey_pricing_rules(survey)
            survey.company = company
            survey.save()
            try:
                from apps.rewards.services import award_xp_for_survey_created

                award_xp_for_survey_created(user=request.user)
            except Exception:
                logger.exception(
                    "Failed to award XP for survey creation user_id=%s",
                    request.user.pk,
                )
            messages.success(
                request,
                _("Survey created as draft. Add questions, then publish to appear in Discover."),
            )
            return redirect("surveys:detail", pk=survey.pk)
    else:
        form = SurveyForm(instance=draft, free_mode=False, company_mode=True)

    return render(
        request,
        "surveys/form.html",
        {
            "form": form,
            "title": _("Create survey"),
            "company": company,
            "company_choices": company_choices,
            "is_platform": is_platform,
            "owner_mode": "company",
            "free_mode": False,
        },
    )


@login_required
def survey_detail(request, pk):
    survey = get_object_or_404(
        Survey.objects.select_related("company"), pk=pk, is_deleted=False
    )
    membership = _get_membership_for_survey(request.user, survey)
    if not _can_edit_survey(request.user, survey) and not membership:
        # Allow company members to view detail even without manage rights
        if not membership and not request.user.is_superuser:
            raise PermissionDenied

    questions = survey.questions.all()
    can_edit = _can_edit_survey(request.user, survey) and survey.is_editable
    from apps.surveys.targeting import has_targeting_rules, targeting_summary

    return render(
        request,
        "surveys/detail.html",
        {
            "survey": survey,
            "questions": questions,
            "can_edit": can_edit,
            "membership": membership,
            "targeting_lines": targeting_summary(survey.targeting),
            "has_targeting": has_targeting_rules(survey.targeting),
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def survey_edit(request, pk):
    survey = get_object_or_404(Survey, pk=pk, is_deleted=False)
    _require_editor(request.user, survey)
    if not survey.is_editable:
        messages.error(
            request, _("This survey is frozen or no longer a draft and cannot be edited.")
        )
        return redirect("surveys:detail", pk=survey.pk)

    if request.method == "POST":
        form = SurveyForm(request.POST, instance=survey, free_mode=False, company_mode=True)
        if form.is_valid():
            survey = form.save(commit=False)
            apply_survey_pricing_rules(survey)
            survey.save()
            messages.success(request, _("Survey updated."))
            return redirect("surveys:detail", pk=survey.pk)
    else:
        form = SurveyForm(instance=survey, free_mode=False, company_mode=True)

    return render(
        request,
        "surveys/form.html",
        {
            "form": form,
            "title": _("Edit survey"),
            "survey": survey,
            "company": survey.company,
            "owner_mode": "company",
            "free_mode": False,
        },
    )


@login_required
@require_POST
def survey_publish(request, pk):
    survey = get_object_or_404(Survey, pk=pk, is_deleted=False)
    _require_editor(request.user, survey)
    try:
        publish_survey(survey)
        survey.refresh_from_db()
        if survey.visibility == Survey.Visibility.PUBLIC:
            members_only = bool((survey.targeting or {}).get("members_only"))
            if members_only:
                messages.success(
                    request,
                    _("Survey is active. Members-only: visible on Discover to company members."),
                )
            else:
                messages.success(
                    request,
                    _("Survey is active and public — it now appears on Discover for everyone."),
                )
        else:
            messages.success(
                request,
                _("Survey is active but private — it will not appear on Discover."),
            )
    except ValueError as e:
        messages.error(request, str(e))
    return redirect("surveys:detail", pk=survey.pk)


@login_required
@require_http_methods(["GET", "POST"])
def question_create(request, survey_pk):
    survey = get_object_or_404(Survey, pk=survey_pk, is_deleted=False)
    _require_editor(request.user, survey)
    if not survey.is_editable:
        messages.error(request, _("This survey is frozen and can no longer be edited."))
        return redirect("surveys:detail", pk=survey.pk)

    if request.method == "POST":
        form = QuestionForm(request.POST, survey=survey)
        if form.is_valid():
            question = form.save(commit=False)
            question.survey = survey
            if question.order == 0:
                last = survey.questions.order_by("-order").first()
                question.order = (last.order + 1) if last else 1
            question.save()
            messages.success(request, _("Question added."))
            return redirect("surveys:detail", pk=survey.pk)
    else:
        form = QuestionForm(survey=survey)

    return render(
        request,
        "surveys/question_form.html",
        {"form": form, "survey": survey, "title": _("Add question")},
    )


@login_required
@require_http_methods(["GET", "POST"])
def question_edit(request, survey_pk, pk):
    survey = get_object_or_404(Survey, pk=survey_pk, is_deleted=False)
    _require_editor(request.user, survey)
    if not survey.is_editable:
        messages.error(request, _("This survey is frozen and can no longer be edited."))
        return redirect("surveys:detail", pk=survey.pk)
    question = get_object_or_404(Question, pk=pk, survey=survey)
    if request.method == "POST":
        form = QuestionForm(request.POST, instance=question, survey=survey)
        if form.is_valid():
            form.save()
            messages.success(request, _("Question updated."))
            return redirect("surveys:detail", pk=survey.pk)
    else:
        form = QuestionForm(instance=question, survey=survey)
    return render(
        request,
        "surveys/question_form.html",
        {"form": form, "survey": survey, "question": question, "title": _("Edit question")},
    )


@login_required
@require_POST
def question_delete(request, survey_pk, pk):
    survey = get_object_or_404(Survey, pk=survey_pk, is_deleted=False)
    _require_editor(request.user, survey)
    if not survey.is_editable:
        messages.error(request, _("This survey is frozen and can no longer be edited."))
        return redirect("surveys:detail", pk=survey.pk)
    question = get_object_or_404(Question, pk=pk, survey=survey)
    question.delete()
    messages.success(request, _("Question deleted."))
    return redirect("surveys:detail", pk=survey.pk)


@require_http_methods(["GET"])
def survey_discover(request):
    from django.core.paginator import Paginator
    from django.utils import timezone

    now = timezone.now()
    # SoftDeleteManager already excludes is_deleted; keep explicit status/visibility rules.
    base_qs = (
        Survey.objects.filter(status=Survey.Status.ACTIVE)
        .filter(visibility=Survey.Visibility.PUBLIC)
        .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))
    )
    qs = (
        base_qs.select_related("company")
        .annotate(question_count=Count("questions"))
        .order_by("-created_at")
    )
    q = (request.GET.get("q") or "").strip()
    category = (request.GET.get("category") or "").strip()
    pricing = (request.GET.get("pricing") or "").strip()
    sort = (request.GET.get("sort") or "newest").strip()
    if q:
        qs = qs.filter(
            Q(title__icontains=q) | Q(description__icontains=q) | Q(category__icontains=q)
        )
    if category:
        qs = qs.filter(category__iexact=category)
    if pricing == "free":
        qs = qs.filter(is_paid=False)
    elif pricing == "paid":
        qs = qs.filter(is_paid=True)
    if sort == "points":
        qs = qs.order_by("-points_reward", "-created_at")
    elif sort == "oldest":
        qs = qs.order_by("created_at")

    # Members-only: hide from non-members.
    # JSON __contains works on PostgreSQL; SQLite (tests) needs a Python fallback.
    from django.db import connection

    member_company_ids: set[int] = set()
    if request.user.is_authenticated:
        member_company_ids = set(
            CompanyMembership.objects.filter(
                user=request.user, is_active=True
            ).values_list("company_id", flat=True)
        )

    if connection.vendor == "postgresql":
        if request.user.is_authenticated:
            qs = qs.exclude(
                Q(targeting__contains={"members_only": True})
                & ~Q(company_id__in=member_company_ids)
            )
        else:
            qs = qs.exclude(targeting__contains={"members_only": True})
    else:
        exclude_ids = [
            s.pk
            for s in qs.only("id", "company_id", "targeting")
            if (s.targeting or {}).get("members_only")
            and s.company_id not in member_company_ids
        ]
        if exclude_ids:
            qs = qs.exclude(pk__in=exclude_ids)

    categories = (
        base_qs.exclude(category="")
        .values_list("category", flat=True)
        .distinct()
        .order_by("category")
    )
    filters_active = bool(q or category or pricing)
    paginator = Paginator(qs, DISCOVER_PAGE_SIZE)
    page_obj = paginator.get_page(request.GET.get("page") or 1)
    completed_ids: set[int] = set()
    if request.user.is_authenticated:
        from apps.responses.models import Response

        completed_ids = set(
            Response.objects.filter(
                participant=request.user,
                status=Response.Status.COMPLETED,
                survey_id__in=[s.id for s in page_obj.object_list],
            ).values_list("survey_id", flat=True)
        )
    query = request.GET.copy()
    query.pop("page", None)
    context = {
        "surveys": page_obj.object_list,
        "page_obj": page_obj,
        "paginator": paginator,
        "q": q,
        "category": category,
        "pricing": pricing,
        "sort": sort,
        "categories": categories,
        "filters_active": filters_active,
        "result_count": paginator.count,
        "completed_ids": completed_ids,
        "querystring": query.urlencode(),
    }
    if request.headers.get("HX-Request") == "true":
        return render(request, "surveys/partials/discover_results.html", context)
    return render(request, "surveys/discover.html", context)


@login_required
def survey_analytics(request, pk):
    survey = get_object_or_404(
        Survey.objects.select_related("company"), pk=pk, is_deleted=False
    )
    membership = _get_membership_for_survey(request.user, survey)
    if not _can_edit_survey(request.user, survey) and not (
        membership and membership.can_manage_surveys
    ):
        if not request.user.is_superuser:
            raise PermissionDenied

    from .analytics import get_survey_analytics

    stats = get_survey_analytics(survey, days=14)
    return render(request, "surveys/analytics.html", stats)
