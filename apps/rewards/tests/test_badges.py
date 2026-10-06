"""Badge evaluation and profile catalog."""
import pytest

from apps.factories import UserFactory
from apps.rewards.models import Badge, UserBadge
from apps.rewards.services import evaluate_badges, get_or_create_progress, list_profile_badges


@pytest.fixture
def sample_badges(db):
    b1 = Badge.objects.create(
        code="first-response",
        name="First Response",
        description="Complete 1 survey",
        icon="✍️",
        xp_bonus=0,
        criteria={"min_surveys_completed": 1},
    )
    b2 = Badge.objects.create(
        code="rising-star",
        name="Rising Star",
        description="Reach level 5",
        icon="⭐",
        xp_bonus=0,
        criteria={"min_level": 5},
    )
    b3 = Badge.objects.create(
        code="trusted-voice",
        name="Trusted Voice",
        description="100 Reputation",
        icon="🛡️",
        xp_bonus=0,
        criteria={"min_honor": 100},
    )
    return b1, b2, b3


@pytest.mark.django_db
def test_evaluate_awards_when_criteria_met(sample_badges):
    user = UserFactory(is_email_verified=True, honor_points=0)
    progress = get_or_create_progress(user)
    progress.surveys_completed = 1
    progress.level = 1
    progress.save(update_fields=["surveys_completed", "level"])

    newly = evaluate_badges(user)
    codes = {ub.badge.code for ub in newly}
    assert "first-response" in codes
    assert UserBadge.objects.filter(user=user, badge__code="first-response").exists()
    assert not UserBadge.objects.filter(user=user, badge__code="rising-star").exists()


@pytest.mark.django_db
def test_evaluate_requires_email_verified(sample_badges):
    user = UserFactory(is_email_verified=False)
    progress = get_or_create_progress(user)
    progress.surveys_completed = 10
    progress.level = 10
    progress.save(update_fields=["surveys_completed", "level"])
    assert evaluate_badges(user) == []
    assert UserBadge.objects.filter(user=user).count() == 0


@pytest.mark.django_db
def test_honor_criteria(sample_badges):
    user = UserFactory(is_email_verified=True, honor_points=150)
    get_or_create_progress(user)
    newly = evaluate_badges(user)
    assert any(ub.badge.code == "trusted-voice" for ub in newly)


@pytest.mark.django_db
def test_list_profile_badges_earned_and_locked(sample_badges):
    user = UserFactory(is_email_verified=True, honor_points=0)
    progress = get_or_create_progress(user)
    progress.surveys_completed = 1
    progress.level = 2
    progress.save(update_fields=["surveys_completed", "level"])
    evaluate_badges(user)

    catalog = list_profile_badges(user)
    assert len(catalog) == 3
    by_code = {item["badge"].code: item for item in catalog}
    assert by_code["first-response"]["earned"] is True
    assert by_code["first-response"]["percent"] == 100
    assert by_code["rising-star"]["earned"] is False
    assert by_code["rising-star"]["current"] == 2
    assert by_code["rising-star"]["target"] == 5
    assert by_code["rising-star"]["percent"] == 40


@pytest.mark.django_db
def test_profile_page_shows_badge_section(client, sample_badges):
    user = UserFactory(is_email_verified=True, honor_points=0)
    client.force_login(user)
    from django.urls import reverse

    r = client.get(reverse("accounts:profile"))
    assert r.status_code == 200
    assert b"Badges" in r.content or b"badge" in r.content.lower()
    assert b"First Response" in r.content or b"Locked" in r.content
