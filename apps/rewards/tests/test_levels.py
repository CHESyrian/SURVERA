"""XP level curve: 25 levels × 1000 XP."""
from apps.rewards.levels import (
    MAX_LEVEL,
    XP_PER_LEVEL,
    level_for_xp,
    xp_for_level,
    xp_into_level,
    xp_to_next_level,
)


def test_level_boundaries():
    assert level_for_xp(0) == 1
    assert level_for_xp(999) == 1
    assert level_for_xp(1000) == 2
    assert level_for_xp(1999) == 2
    assert level_for_xp(1000 * 24) == 25
    assert level_for_xp(1000 * 24 + 5000) == 25


def test_xp_for_level():
    assert xp_for_level(1) == 0
    assert xp_for_level(2) == 1000
    assert xp_for_level(25) == 24000


def test_into_and_remaining():
    assert xp_into_level(500) == 500
    assert xp_to_next_level(500) == 500
    assert xp_to_next_level(24000) == 0
    assert MAX_LEVEL == 25
    assert XP_PER_LEVEL == 1000
