"""
Honor points and trust levels for SURVERA.

Honor is a reputation ledger (separate from survey reward Points and XP).
Trust level is derived from honor bands — never set by hand.

Also used by the report penalties catalog (warnings, rank reduction, etc.).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from django.db import transaction
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Grant amounts (one-time onboarding)
# ---------------------------------------------------------------------------
HONOR_REGISTRATION = 10
HONOR_EMAIL_VERIFIED = 20
HONOR_PROFILE_BASIC = 20

# ---------------------------------------------------------------------------
# Trust levels (1–7). Bands are inclusive on both ends except Distinguished.
# Honor 0 is treated as Newcomer floor (e.g. after future penalties).
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TrustLevelBand:
    level: int
    code: str
    name: str  # English label; UI can translate via gettext on code
    min_honor: int
    max_honor: int | None  # None = no upper bound


TRUST_LEVEL_BANDS: tuple[TrustLevelBand, ...] = (
    TrustLevelBand(1, "newcomer", "Newcomer", 0, 99),
    TrustLevelBand(2, "contributor", "Contributor", 100, 199),
    TrustLevelBand(3, "trusted", "Trusted", 200, 399),
    TrustLevelBand(4, "reliable", "Reliable", 400, 599),
    TrustLevelBand(5, "proven", "Proven", 600, 899),
    TrustLevelBand(6, "elite", "Elite", 900, 1499),
    TrustLevelBand(7, "distinguished", "Distinguished", 1500, None),
)

# Optional 0–100 projection of reputation level (kept for admin/compat).
# Targeting uses reputation level (trust_level 1–7 from honor_points), not this score.
TRUST_SCORE_BY_LEVEL: dict[int, int] = {
    1: 15,
    2: 30,
    3: 45,
    4: 60,
    5: 75,
    6: 90,
    7: 100,
}


def level_for_honor(honor_points: int) -> int:
    """Return trust level 1–7 for a given honor balance."""
    pts = max(0, int(honor_points or 0))
    for band in reversed(TRUST_LEVEL_BANDS):
        if pts >= band.min_honor:
            return band.level
    return 1


def band_for_level(level: int) -> TrustLevelBand:
    for band in TRUST_LEVEL_BANDS:
        if band.level == level:
            return band
    return TRUST_LEVEL_BANDS[0]


def trust_score_for_level(level: int) -> int:
    return TRUST_SCORE_BY_LEVEL.get(int(level), 15)


def honor_progress_in_level(honor_points: int) -> tuple[int, int | None, int]:
    """
    Returns (points_into_level, points_needed_for_next_or_None, percent 0–100).
    At Distinguished, points_needed is None and percent is 100.
    """
    pts = max(0, int(honor_points or 0))
    level = level_for_honor(pts)
    band = band_for_level(level)
    into = pts - band.min_honor
    if band.max_honor is None:
        return into, None, 100
    span = band.max_honor - band.min_honor + 1
    need = band.max_honor + 1 - pts
    pct = min(100, int(100 * into / span)) if span else 100
    return into, max(0, need), pct


@transaction.atomic
def apply_honor_delta(
    *,
    user,
    amount: int,
    reason: str,
    note: str = "",
    created_by=None,
    once: bool = False,
) -> object | None:
    """
    Apply an honor delta, refresh trust_level + trust_score, write HonorEvent.

    If once=True and an event with the same reason already exists for the user,
    no-op and return None.
    """
    from .models import HonorEvent, User

    if user is None or amount == 0:
        return None

    if once and HonorEvent.objects.filter(user=user, reason=reason).exists():
        return None

    # Lock user row for concurrent grants
    user = User.objects.select_for_update().get(pk=user.pk)
    old_honor = int(user.honor_points or 0)
    new_honor = max(0, old_honor + int(amount))  # floor at 0 for future penalties
    old_level = int(user.trust_level or 1)
    new_level = level_for_honor(new_honor)
    new_score = trust_score_for_level(new_level)

    user.honor_points = new_honor
    user.trust_level = new_level
    user.trust_score = new_score
    user.save(update_fields=["honor_points", "trust_level", "trust_score"])

    event = HonorEvent.objects.create(
        user=user,
        amount=int(amount),
        balance_after=new_honor,
        reason=reason,
        note=(note or "")[:300],
        created_by=created_by,
        level_after=new_level,
    )

    if new_level != old_level:
        logger.info(
            "User %s trust level %s → %s (honor %s)",
            user.pk,
            old_level,
            new_level,
            new_honor,
        )
    return event


def grant_registration_honor(user) -> object | None:
    """+10 once when the account is created."""
    from .models import HonorEvent

    return apply_honor_delta(
        user=user,
        amount=HONOR_REGISTRATION,
        reason=HonorEvent.Reason.REGISTRATION,
        note="Account registration",
        once=True,
    )


def grant_email_verified_honor(user) -> object | None:
    """+20 once when email is verified."""
    from .models import HonorEvent

    return apply_honor_delta(
        user=user,
        amount=HONOR_EMAIL_VERIFIED,
        reason=HonorEvent.Reason.EMAIL_VERIFIED,
        note="Email verified",
        once=True,
    )


def is_basic_profile_complete(user) -> bool:
    """Basic account info: date of birth + gender (same bar as profile UI)."""
    return bool(getattr(user, "date_of_birth", None) and (getattr(user, "gender", None) or "").strip())


def grant_profile_basic_honor(user) -> object | None:
    """+20 once when basic profile fields are filled."""
    from .models import HonorEvent

    if not is_basic_profile_complete(user):
        return None
    return apply_honor_delta(
        user=user,
        amount=HONOR_PROFILE_BASIC,
        reason=HonorEvent.Reason.PROFILE_BASIC,
        note="Basic profile completed",
        once=True,
    )


def sync_trust_fields_from_honor(user, *, save: bool = True) -> None:
    """Recompute trust_level and trust_score from honor_points (repair helper)."""
    level = level_for_honor(user.honor_points)
    score = trust_score_for_level(level)
    user.trust_level = level
    user.trust_score = score
    if save:
        user.save(update_fields=["trust_level", "trust_score"])


@transaction.atomic
def reduce_rank_levels(
    *,
    user,
    levels: int = 1,
    reason: str | None = None,
    note: str = "",
    created_by=None,
) -> object | None:
    """
    Drop the user by `levels` trust ranks by setting honor to the top of the
    target band (e.g. level 7 → 6 sets honor to 1499).
    Floors at level 1.
    """
    from .models import HonorEvent, User

    levels = max(1, int(levels or 1))
    user = User.objects.select_for_update().get(pk=user.pk)
    current = int(user.trust_level or level_for_honor(user.honor_points or 0))
    target = max(1, current - levels)
    if target >= current:
        return None

    band = band_for_level(target)
    # Sit at the top of the target band when it has a max; else at min.
    if band.max_honor is not None:
        new_honor = band.max_honor
    else:
        new_honor = band.min_honor

    old_honor = int(user.honor_points or 0)
    delta = new_honor - old_honor  # typically negative
    if delta == 0 and int(user.trust_level or 1) == target:
        return None

    user.honor_points = max(0, new_honor)
    user.trust_level = target
    user.trust_score = trust_score_for_level(target)
    user.save(update_fields=["honor_points", "trust_level", "trust_score"])

    event = HonorEvent.objects.create(
        user=user,
        amount=delta,
        balance_after=user.honor_points,
        reason=reason or HonorEvent.Reason.REPORT_PENALTY,
        note=(note or f"Rank reduced to level {target}")[:300],
        created_by=created_by,
        level_after=target,
    )
    logger.info(
        "User %s rank %s → %s (honor %s → %s)",
        user.pk,
        current,
        target,
        old_honor,
        user.honor_points,
    )
    return event
