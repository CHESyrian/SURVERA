"""Leaderboard queries: Reputation, XP, Companies (top 100, paged)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.contrib.auth import get_user_model
from django.db.models import Count, Q

from apps.companies.models import Company
from apps.responses.models import Response
from apps.rewards.models import UserProgress

User = get_user_model()

TOP_N = 100
PAGE_SIZE = 25

TAB_REPUTATION = "reputation"
TAB_XP = "xp"
TAB_COMPANIES = "companies"
VALID_TABS = frozenset({TAB_REPUTATION, TAB_XP, TAB_COMPANIES})


@dataclass
class LeaderboardRow:
    rank: int
    score: int
    label: str
    subtitle: str = ""
    object_id: int | None = None
    is_self: bool = False
    medal: str | None = None  # gold | silver | bronze


@dataclass
class LeaderboardPage:
    tab: str
    rows: list[LeaderboardRow]
    offset: int
    next_offset: int | None
    total_capped: int  # min(real_total, TOP_N)
    viewer_row: LeaderboardRow | None  # shown below list when outside current window / top 100


def _medal_for(rank: int) -> str | None:
    if rank == 1:
        return "gold"
    if rank == 2:
        return "silver"
    if rank == 3:
        return "bronze"
    return None


def _active_users_qs():
    return User.objects.filter(is_active=True, closed_at__isnull=True)


def reputation_queryset():
    return _active_users_qs().order_by("-honor_points", "id")


def xp_queryset():
    # Prefer UserProgress; users without a row are treated as 0 XP (excluded from top unless all zero).
    return (
        UserProgress.objects.select_related("user")
        .filter(user__is_active=True, user__closed_at__isnull=True)
        .order_by("-xp_total", "user_id")
    )


def companies_queryset():
    """Rank active companies by completed response count on their surveys."""
    return (
        Company.objects.filter(status=Company.Status.ACTIVE)
        .annotate(
            score=Count(
                "surveys__responses",
                filter=Q(surveys__responses__status=Response.Status.COMPLETED),
                distinct=True,
            )
        )
        .order_by("-score", "id")
    )


def _slice(qs, offset: int) -> tuple[list, int, int | None]:
    """Return items for [offset, offset+PAGE_SIZE) within top TOP_N, next_offset or None."""
    offset = max(0, int(offset or 0))
    if offset >= TOP_N:
        return [], TOP_N, None
    limit = min(PAGE_SIZE, TOP_N - offset)
    # Fetch one extra to know if more pages exist within TOP_N
    batch = list(qs[offset : offset + limit + 1])
    has_more = len(batch) > limit and (offset + limit) < TOP_N
    items = batch[:limit]
    # Approximate capped total: if we got a full page and more, at least offset+limit+1
    if has_more:
        total_capped = min(TOP_N, offset + limit + 1)
        next_offset = offset + limit
    else:
        total_capped = offset + len(items)
        next_offset = None
    return items, total_capped, next_offset


def _reputation_rows(offset: int, viewer) -> LeaderboardPage:
    qs = reputation_queryset()
    items, total_capped, next_offset = _slice(qs, offset)
    rows: list[LeaderboardRow] = []
    for i, user in enumerate(items):
        rank = offset + i + 1
        rows.append(
            LeaderboardRow(
                rank=rank,
                score=int(user.honor_points or 0),
                label=user.username or user.email,
                subtitle=user.trust_level_label,
                object_id=user.pk,
                is_self=bool(viewer and viewer.is_authenticated and viewer.pk == user.pk),
                medal=_medal_for(rank),
            )
        )
    viewer_row = _viewer_reputation(viewer, offset, rows)
    return LeaderboardPage(
        tab=TAB_REPUTATION,
        rows=rows,
        offset=offset,
        next_offset=next_offset,
        total_capped=total_capped,
        viewer_row=viewer_row,
    )


def _viewer_reputation(viewer, offset: int, rows: list[LeaderboardRow]) -> LeaderboardRow | None:
    if not viewer or not viewer.is_authenticated:
        return None
    if any(r.is_self for r in rows):
        return None
    if not viewer.is_active or viewer.closed_at:
        return None
    score = int(viewer.honor_points or 0)
    higher = _active_users_qs().filter(honor_points__gt=score).count()
    rank = higher + 1
    if rank > TOP_N or rank <= offset or rank > offset + len(rows):
        return LeaderboardRow(
            rank=rank,
            score=score,
            label=viewer.username or viewer.email,
            subtitle=viewer.trust_level_label,
            object_id=viewer.pk,
            is_self=True,
            medal=_medal_for(rank),
        )
    return None


def _xp_rows(offset: int, viewer) -> LeaderboardPage:
    qs = xp_queryset()
    items, total_capped, next_offset = _slice(qs, offset)
    rows: list[LeaderboardRow] = []
    for i, progress in enumerate(items):
        rank = offset + i + 1
        user = progress.user
        rows.append(
            LeaderboardRow(
                rank=rank,
                score=int(progress.xp_total or 0),
                label=user.username or user.email,
                subtitle=f"L{progress.level}",
                object_id=user.pk,
                is_self=bool(viewer and viewer.is_authenticated and viewer.pk == user.pk),
                medal=_medal_for(rank),
            )
        )
    viewer_row = _viewer_xp(viewer, offset, rows)
    return LeaderboardPage(
        tab=TAB_XP,
        rows=rows,
        offset=offset,
        next_offset=next_offset,
        total_capped=total_capped,
        viewer_row=viewer_row,
    )


def _viewer_xp(viewer, offset: int, rows: list[LeaderboardRow]) -> LeaderboardRow | None:
    if not viewer or not viewer.is_authenticated:
        return None
    if any(r.is_self for r in rows):
        return None
    if not viewer.is_active or viewer.closed_at:
        return None
    progress = UserProgress.objects.filter(user=viewer).first()
    score = int(progress.xp_total) if progress else 0
    level = progress.level if progress else 1
    higher = UserProgress.objects.filter(
        user__is_active=True,
        user__closed_at__isnull=True,
        xp_total__gt=score,
    ).count()
    # Users with no progress row count as 0; they don't increase "higher"
    rank = higher + 1
    if rank > TOP_N or rank <= offset or rank > offset + len(rows):
        return LeaderboardRow(
            rank=rank,
            score=score,
            label=viewer.username or viewer.email,
            subtitle=f"L{level}",
            object_id=viewer.pk,
            is_self=True,
            medal=_medal_for(rank),
        )
    return None


def _company_rows(offset: int, viewer) -> LeaderboardPage:
    qs = companies_queryset()
    items, total_capped, next_offset = _slice(qs, offset)
    rows: list[LeaderboardRow] = []
    viewer_company_ids: set[int] = set()
    if viewer and viewer.is_authenticated:
        viewer_company_ids = set(
            viewer.company_memberships.filter(is_active=True).values_list("company_id", flat=True)
        )
    for i, company in enumerate(items):
        rank = offset + i + 1
        score = int(getattr(company, "score", 0) or 0)
        rows.append(
            LeaderboardRow(
                rank=rank,
                score=score,
                label=company.name,
                subtitle=company.slug,
                object_id=company.pk,
                is_self=company.pk in viewer_company_ids,
                medal=_medal_for(rank),
            )
        )
    viewer_row = _viewer_company(viewer, offset, rows, viewer_company_ids)
    return LeaderboardPage(
        tab=TAB_COMPANIES,
        rows=rows,
        offset=offset,
        next_offset=next_offset,
        total_capped=total_capped,
        viewer_row=viewer_row,
    )


def _viewer_company(
    viewer, offset: int, rows: list[LeaderboardRow], company_ids: set[int]
) -> LeaderboardRow | None:
    if not company_ids:
        return None
    if any(r.is_self for r in rows):
        return None
    # Best-ranked company the viewer belongs to
    ranked = list(companies_queryset()[:TOP_N])
    id_to_rank = {c.pk: idx + 1 for idx, c in enumerate(ranked)}
    best: tuple[int, Any] | None = None
    for cid in company_ids:
        r = id_to_rank.get(cid)
        if r is None:
            # Outside top 100 — compute rank among all
            company = Company.objects.filter(pk=cid, status=Company.Status.ACTIVE).annotate(
                score=Count(
                    "surveys__responses",
                    filter=Q(surveys__responses__status=Response.Status.COMPLETED),
                    distinct=True,
                )
            ).first()
            if not company:
                continue
            score = int(company.score or 0)
            higher = (
                Company.objects.filter(status=Company.Status.ACTIVE)
                .annotate(
                    score=Count(
                        "surveys__responses",
                        filter=Q(surveys__responses__status=Response.Status.COMPLETED),
                        distinct=True,
                    )
                )
                .filter(score__gt=score)
                .count()
            )
            r = higher + 1
            if best is None or r < best[0]:
                best = (r, company)
        else:
            company = next(c for c in ranked if c.pk == cid)
            if best is None or r < best[0]:
                best = (r, company)
    if not best:
        return None
    rank, company = best
    score = int(getattr(company, "score", 0) or 0)
    if rank > TOP_N or rank <= offset or rank > offset + len(rows):
        return LeaderboardRow(
            rank=rank,
            score=score,
            label=company.name,
            subtitle=company.slug,
            object_id=company.pk,
            is_self=True,
            medal=_medal_for(rank),
        )
    return None


def get_leaderboard(tab: str, offset: int = 0, viewer=None) -> LeaderboardPage:
    tab = tab if tab in VALID_TABS else TAB_REPUTATION
    offset = max(0, int(offset or 0))
    if tab == TAB_XP:
        return _xp_rows(offset, viewer)
    if tab == TAB_COMPANIES:
        return _company_rows(offset, viewer)
    return _reputation_rows(offset, viewer)


def score_label_for_tab(tab: str) -> str:
    if tab == TAB_XP:
        return "XP"
    if tab == TAB_COMPANIES:
        return "Responses"
    return "Reputation"
