"""XP thresholds and constants.

Levels: 1–25. Each level requires 1000 XP (flat).
Level 1 starts at 0 cumulative XP; level 25 is the maximum.
"""
from __future__ import annotations

XP_SURVEY_COMPLETION = 25
XP_SURVEY_CREATED = 15
XP_PROFILE_COMPLETE = 20
XP_DAILY_LOGIN = 5

# Task rewards
XP_TASK_DAILY = 50
XP_TASK_WEEKLY = 100

MAX_LEVEL = 25
XP_PER_LEVEL = 1000


def xp_for_level(level: int) -> int:
    """Cumulative XP required to *reach* this level (level 1 = 0)."""
    if level <= 1:
        return 0
    level = min(int(level), MAX_LEVEL + 1)
    return (level - 1) * XP_PER_LEVEL


def level_for_xp(xp: int) -> int:
    """Level for a cumulative XP total, clamped to MAX_LEVEL."""
    xp = max(0, int(xp or 0))
    level = 1 + (xp // XP_PER_LEVEL)
    return min(level, MAX_LEVEL)


def xp_into_level(xp: int) -> int:
    """XP progress within the current level (0 … XP_PER_LEVEL-1), or full at max."""
    xp = max(0, int(xp or 0))
    if level_for_xp(xp) >= MAX_LEVEL:
        return XP_PER_LEVEL
    return xp % XP_PER_LEVEL


def xp_for_next_level(xp: int) -> int:
    """Cumulative XP needed for the next level (same as current total if maxed)."""
    lvl = level_for_xp(xp)
    if lvl >= MAX_LEVEL:
        return xp_for_level(MAX_LEVEL)
    return xp_for_level(lvl + 1)


def xp_to_next_level(xp: int) -> int:
    """Remaining XP until next level (0 if maxed)."""
    if level_for_xp(xp) >= MAX_LEVEL:
        return 0
    return xp_for_next_level(xp) - max(0, int(xp or 0))
