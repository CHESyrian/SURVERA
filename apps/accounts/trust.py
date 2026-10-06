"""Legacy trust_score helpers (admin/audit only).

Product trust is Reputation: honor_points + trust_level (1–7). Prefer honor.py.
"""
from __future__ import annotations

from django.db import transaction

from .models import TrustEvent, User

DEFAULT_TRUST_SCORE = 50
MIN_TRUST = 0
MAX_TRUST = 100


def clamp_trust(score: int) -> int:
    return max(MIN_TRUST, min(MAX_TRUST, int(score)))


@transaction.atomic
def record_trust_change(
    *,
    user: User,
    new_score: int,
    reason: str = TrustEvent.Reason.ADMIN_ADJUST,
    note: str = "",
    created_by: User | None = None,
) -> TrustEvent:
    """
    Set user.trust_score and append a TrustEvent (legacy).

    Does not change honor_points or reputation level. Prefer apply_honor_delta.
    """
    new_score = clamp_trust(new_score)
    old = int(user.trust_score or DEFAULT_TRUST_SCORE)
    if new_score == old and not note:
        return TrustEvent(
            user=user,
            old_score=old,
            new_score=old,
            delta=0,
            reason=reason,
            note=note or "no change",
            created_by=created_by,
        )

    user.trust_score = new_score
    user.save(update_fields=["trust_score"])
    return TrustEvent.objects.create(
        user=user,
        old_score=old,
        new_score=new_score,
        delta=new_score - old,
        reason=reason,
        note=(note or "")[:300],
        created_by=created_by,
    )
