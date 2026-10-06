"""Honor points and trust level bands + onboarding grants."""
import pytest

from apps.accounts.honor import (
    HONOR_EMAIL_VERIFIED,
    HONOR_PROFILE_BASIC,
    HONOR_REGISTRATION,
    band_for_level,
    grant_email_verified_honor,
    grant_profile_basic_honor,
    grant_registration_honor,
    level_for_honor,
    trust_score_for_level,
)
from apps.accounts.models import HonorEvent
from apps.accounts.verification import mark_email_verified
from apps.factories import UserFactory


@pytest.mark.django_db
class TestLevelBands:
    def test_boundaries(self):
        assert level_for_honor(0) == 1
        assert level_for_honor(1) == 1
        assert level_for_honor(99) == 1
        assert level_for_honor(100) == 2
        assert level_for_honor(199) == 2
        assert level_for_honor(200) == 3
        assert level_for_honor(399) == 3
        assert level_for_honor(400) == 4
        assert level_for_honor(599) == 4
        assert level_for_honor(600) == 5
        assert level_for_honor(899) == 5
        assert level_for_honor(900) == 6
        assert level_for_honor(1499) == 6
        assert level_for_honor(1500) == 7
        assert level_for_honor(99999) == 7

    def test_band_labels(self):
        assert band_for_level(1).name == "Newcomer"
        assert band_for_level(2).name == "Contributor"
        assert band_for_level(3).name == "Trusted"
        assert band_for_level(4).name == "Reliable"
        assert band_for_level(5).name == "Proven"
        assert band_for_level(6).name == "Elite"
        assert band_for_level(7).name == "Distinguished"

    def test_trust_score_projection(self):
        assert trust_score_for_level(1) == 15
        assert trust_score_for_level(7) == 100


@pytest.mark.django_db
class TestOnboardingGrants:
    def test_registration_grant_on_create(self):
        user = UserFactory()
        user.refresh_from_db()
        assert user.honor_points == HONOR_REGISTRATION
        assert user.trust_level == 1
        assert HonorEvent.objects.filter(
            user=user, reason=HonorEvent.Reason.REGISTRATION
        ).count() == 1
        # Idempotent
        assert grant_registration_honor(user) is None
        user.refresh_from_db()
        assert user.honor_points == HONOR_REGISTRATION

    def test_email_verified_grant(self):
        user = UserFactory()
        user.refresh_from_db()
        base = user.honor_points
        mark_email_verified(user)
        user.refresh_from_db()
        assert user.is_email_verified is True
        assert user.honor_points == base + HONOR_EMAIL_VERIFIED
        assert HonorEvent.objects.filter(
            user=user, reason=HonorEvent.Reason.EMAIL_VERIFIED
        ).exists()
        # Once only
        assert grant_email_verified_honor(user) is None
        user.refresh_from_db()
        assert user.honor_points == base + HONOR_EMAIL_VERIFIED

    def test_profile_basic_grant(self):
        user = UserFactory()
        user.refresh_from_db()
        base = user.honor_points
        user.date_of_birth = "1990-01-15"
        user.gender = "female"
        user.save(update_fields=["date_of_birth", "gender"])
        event = grant_profile_basic_honor(user)
        assert event is not None
        user.refresh_from_db()
        assert user.honor_points == base + HONOR_PROFILE_BASIC
        assert grant_profile_basic_honor(user) is None

    def test_full_onboarding_stays_newcomer(self):
        """10+20+20 = 50 → still Newcomer (1–99)."""
        user = UserFactory()
        mark_email_verified(user)
        user.date_of_birth = "1990-01-15"
        user.gender = "male"
        user.save(update_fields=["date_of_birth", "gender"])
        grant_profile_basic_honor(user)
        user.refresh_from_db()
        assert user.honor_points == (
            HONOR_REGISTRATION + HONOR_EMAIL_VERIFIED + HONOR_PROFILE_BASIC
        )
        assert user.honor_points == 50
        assert user.trust_level == 1
        assert user.trust_score == 15
