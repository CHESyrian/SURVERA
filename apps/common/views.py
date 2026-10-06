"""Shared site views."""
from django.db.models import Count, Q
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_http_methods


@require_http_methods(["GET"])
def home(request):
    from apps.surveys.limits import can_create_survey, user_manageable_companies
    from apps.surveys.models import Survey
    from apps.responses.models import Response

    now = timezone.now()
    public_active = (
        Survey.objects.filter(
            status=Survey.Status.ACTIVE,
            visibility=Survey.Visibility.PUBLIC,
        )
        .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))
        .select_related("company")
        .annotate(question_count=Count("questions"))
        .order_by("-created_at")
    )
    active_count = public_active.count()
    featured = list(public_active[:6])

    can_create = False
    has_company_editor = False
    progress = None
    points = 0
    completed_ids: set[int] = set()

    if request.user.is_authenticated:
        can_create, _ = can_create_survey(request.user)
        has_company_editor = bool(user_manageable_companies(request.user)) or request.user.is_superuser
        try:
            from apps.rewards.services import get_or_create_progress, get_points_balance

            progress = get_or_create_progress(request.user)
            points = get_points_balance(request.user)
        except Exception:
            progress = None
            points = 0

        if featured:
            completed_ids = set(
                Response.objects.filter(
                    participant=request.user,
                    status=Response.Status.COMPLETED,
                    survey_id__in=[s.pk for s in featured],
                ).values_list("survey_id", flat=True)
            )

    return render(
        request,
        "home.html",
        {
            "active_count": active_count,
            "featured": featured,
            "completed_survey_ids": completed_ids,
            "can_create_survey": can_create,
            "has_company_editor": has_company_editor,
            "progress": progress,
            "points": points,
        },
    )
