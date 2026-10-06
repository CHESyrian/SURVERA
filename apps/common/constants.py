"""
Shared application constants for SURVERA.

Import from here instead of scattering magic numbers/strings across the codebase.
"""

from __future__ import annotations

from typing import Final

from django.utils.translation import gettext_lazy as _

# ---------------------------------------------------------------------------
# Platform / branding
# ---------------------------------------------------------------------------
APP_NAME: Final[str] = "SURVERA"
PLATFORM_COMPANY_NAME: Final[str] = "SURVERA"
PLATFORM_COMPANY_SLUG: Final[str] = "survera"

# ---------------------------------------------------------------------------
# Survey categories (create form combobox + Discover filters)
# value stored on Survey.category; label shown in UI
# ---------------------------------------------------------------------------
SURVEY_CATEGORY_CHOICES: Final[tuple[tuple[str, object], ...]] = (
    ("", "—"),
    ("market_research", _("Market research")),
    ("customer_feedback", _("Customer feedback")),
    ("product", _("Product")),
    ("ux", _("UX / usability")),
    ("hr", _("HR / workplace")),
    ("education", _("Education")),
    ("health", _("Health")),
    ("politics", _("Politics / public opinion")),
    ("events", _("Events")),
    ("other", _("Other")),
)

SURVEY_CATEGORY_VALUES: Final[frozenset[str]] = frozenset(
    v for v, _ in SURVEY_CATEGORY_CHOICES if v
)

SURVEY_CATEGORY_LABELS: Final[dict[str, object]] = {
    v: label for v, label in SURVEY_CATEGORY_CHOICES if v
}

# ---------------------------------------------------------------------------
# Survey limits & defaults
# ---------------------------------------------------------------------------
DEFAULT_RATING_MAX: Final[int] = 5
DEFAULT_SCALE_MIN: Final[int] = 1
DEFAULT_SCALE_MAX: Final[int] = 10
MIN_CHOICES_PER_QUESTION: Final[int] = 2
DISCOVER_PAGE_SIZE: Final[int] = 12

SURVEY_SORT_OPTIONS: Final[tuple[tuple[str, str], ...]] = (
    ("newest", "Newest"),
    ("oldest", "Oldest"),
    ("points", "Points"),
)

SURVEY_PRICING_FILTERS: Final[tuple[tuple[str, str], ...]] = (
    ("", "All"),
    ("free", "Free"),
    ("paid", "Paid"),
)

# ---------------------------------------------------------------------------
# Rewards / progression defaults (mirrors rewards.levels when needed)
# ---------------------------------------------------------------------------
XP_SURVEY_COMPLETION: Final[int] = 25
XP_SURVEY_CREATED: Final[int] = 15
XP_PROFILE_COMPLETE: Final[int] = 20
XP_DAILY_LOGIN: Final[int] = 5

DEFAULT_TRUST_SCORE: Final[int] = 50
TRUST_SCORE_MIN: Final[int] = 0
TRUST_SCORE_MAX: Final[int] = 100

# ---------------------------------------------------------------------------
# Roles that can manage surveys (string values match CompanyMembership.Role)
# ---------------------------------------------------------------------------
SURVEY_MANAGER_ROLES: Final[tuple[str, ...]] = (
    "owner",
    "moderator",
    "admin",
)

# ---------------------------------------------------------------------------
# Supported UI languages
# ---------------------------------------------------------------------------
LANGUAGE_CHOICES: Final[tuple[tuple[str, str], ...]] = (
    ("en", "English"),
    ("ar", "العربية"),
)

DEFAULT_LANGUAGE: Final[str] = "en"
