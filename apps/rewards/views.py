"""Rewards / tasks / leaderboard UI."""
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils.translation import gettext as _

from apps.rewards.leaderboard import (
    PAGE_SIZE,
    TAB_COMPANIES,
    TAB_REPUTATION,
    TAB_XP,
    VALID_TABS,
    get_leaderboard,
    score_label_for_tab,
)
from apps.rewards.tasks_service import list_user_tasks


@login_required
def tasks_page(request):
    tasks = list_user_tasks(request.user)
    return render(
        request,
        "rewards/tasks.html",
        {
            "daily_tasks": tasks["daily"],
            "weekly_tasks": tasks["weekly"],
            "general_tasks": tasks["general"],
        },
    )


def leaderboard_page(request):
    """Public leaderboard with three tabs (Reputation / XP / Companies)."""
    tab = request.GET.get("tab", TAB_REPUTATION)
    if tab not in VALID_TABS:
        tab = TAB_REPUTATION
    page = get_leaderboard(tab, offset=0, viewer=request.user)
    return render(
        request,
        "rewards/leaderboard.html",
        {
            "page": page,
            "tab": tab,
            "score_label": score_label_for_tab(tab),
            "page_size": PAGE_SIZE,
            "tabs": [
                {"id": TAB_REPUTATION, "label": _("Reputation")},
                {"id": TAB_XP, "label": _("XP")},
                {"id": TAB_COMPANIES, "label": _("Companies")},
            ],
        },
    )


def leaderboard_rows(request):
    """HTMX partial: next slice of rows (lazy load / load more)."""
    tab = request.GET.get("tab", TAB_REPUTATION)
    if tab not in VALID_TABS:
        tab = TAB_REPUTATION
    try:
        offset = int(request.GET.get("offset", 0))
    except (TypeError, ValueError):
        offset = 0
    page = get_leaderboard(tab, offset=offset, viewer=request.user)
    return render(
        request,
        "rewards/partials/leaderboard_rows.html",
        {
            "page": page,
            "tab": tab,
            "score_label": score_label_for_tab(tab),
        },
    )
