"""Trust score honesty: fixed default + audited changes via TrustEvent."""
import pytest

from apps.accounts.models import TrustEvent
from apps.accounts.trust import clamp_trust, record_trust_change
from apps.factories import UserFactory


@pytest.mark.django_db
class TestTrustDefaults:
    def test_new_user_score_from_honor_level(self):
        user = UserFactory()
        user.refresh_from_db()
        # Registration honor → level 1 → score 15
        assert user.trust_level == 1
        assert user.trust_score == 15


@pytest.mark.django_db
class TestRecordTrustChange:
    def test_updates_score_and_creates_event(self):
        user = UserFactory()
        admin = UserFactory(is_staff=True)
        event = record_trust_change(
            user=user,
            new_score=70,
            reason=TrustEvent.Reason.ADMIN_ADJUST,
            note="Manual boost",
            created_by=admin,
        )
        user.refresh_from_db()
        assert user.trust_score == 70
        assert event.old_score == 15
        assert event.new_score == 70
        assert event.delta == 55
        assert TrustEvent.objects.filter(user=user).count() == 1

    def test_clamps_to_0_100(self):
        assert clamp_trust(-5) == 0
        assert clamp_trust(150) == 100
        user = UserFactory()
        record_trust_change(user=user, new_score=200)
        user.refresh_from_db()
        assert user.trust_score == 100
