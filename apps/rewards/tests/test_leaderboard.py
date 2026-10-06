"""Leaderboard: reputation, XP, companies — paging and viewer rank."""
import pytest
from django.urls import reverse

from apps.factories import CompanyFactory, CompanyMembershipFactory, ResponseFactory, SurveyFactory, UserFactory
from apps.responses.models import Response
from apps.rewards.leaderboard import (
    PAGE_SIZE,
    TAB_COMPANIES,
    TAB_REPUTATION,
    TAB_XP,
    TOP_N,
    get_leaderboard,
)
from apps.rewards.models import UserProgress
from apps.rewards.services import get_or_create_progress


@pytest.mark.django_db
def test_reputation_order_and_medals():
    u1 = UserFactory(honor_points=300, username="top")
    u2 = UserFactory(honor_points=200, username="second")
    u3 = UserFactory(honor_points=100, username="third")
    UserFactory(honor_points=50, username="fourth")

    page = get_leaderboard(TAB_REPUTATION, offset=0, viewer=None)
    assert [r.label for r in page.rows[:3]] == ["top", "second", "third"]
    assert page.rows[0].medal == "gold"
    assert page.rows[1].medal == "silver"
    assert page.rows[2].medal == "bronze"
    assert page.rows[3].medal is None
    assert page.rows[0].score == 300
    assert u1.pk and u2.pk and u3.pk


@pytest.mark.django_db
def test_xp_tab_orders_by_xp_total():
    a = UserFactory(username="alpha")
    b = UserFactory(username="beta")
    pa = get_or_create_progress(a)
    pb = get_or_create_progress(b)
    pa.xp_total = 500
    pa.level = 5
    pa.save(update_fields=["xp_total", "level"])
    pb.xp_total = 900
    pb.level = 9
    pb.save(update_fields=["xp_total", "level"])

    page = get_leaderboard(TAB_XP, offset=0)
    assert page.rows[0].label == "beta"
    assert page.rows[0].score == 900
    assert page.rows[1].label == "alpha"


@pytest.mark.django_db
def test_companies_rank_by_completed_responses():
    c1 = CompanyFactory(name="Alpha Co")
    c2 = CompanyFactory(name="Beta Co")
    s1 = SurveyFactory(company=c1)
    s2 = SurveyFactory(company=c2)
    ResponseFactory(survey=s1, status=Response.Status.COMPLETED)
    ResponseFactory(survey=s1, status=Response.Status.COMPLETED)
    ResponseFactory(survey=s2, status=Response.Status.COMPLETED)
    ResponseFactory(survey=s2, status=Response.Status.IN_PROGRESS)

    page = get_leaderboard(TAB_COMPANIES, offset=0)
    assert page.rows[0].label == "Alpha Co"
    assert page.rows[0].score == 2
    assert page.rows[1].label == "Beta Co"
    assert page.rows[1].score == 1


@pytest.mark.django_db
def test_pagination_page_size_and_cap():
    for i in range(30):
        UserFactory(honor_points=1000 - i, username=f"u{i:03d}")

    page0 = get_leaderboard(TAB_REPUTATION, offset=0)
    assert len(page0.rows) == PAGE_SIZE
    assert page0.next_offset == PAGE_SIZE

    page1 = get_leaderboard(TAB_REPUTATION, offset=PAGE_SIZE)
    assert len(page1.rows) == 5  # 30 total
    assert page1.next_offset is None
    assert page1.rows[0].rank == PAGE_SIZE + 1


@pytest.mark.django_db
def test_viewer_outside_top_shown():
    for i in range(5):
        UserFactory(honor_points=500 - i)
    me = UserFactory(honor_points=1, username="me-low")

    page = get_leaderboard(TAB_REPUTATION, offset=0, viewer=me)
    assert page.viewer_row is not None
    assert page.viewer_row.is_self
    assert page.viewer_row.rank == 6
    assert page.viewer_row.score == 1


@pytest.mark.django_db
def test_viewer_in_list_no_footer():
    me = UserFactory(honor_points=999, username="champ")
    UserFactory(honor_points=10)
    page = get_leaderboard(TAB_REPUTATION, offset=0, viewer=me)
    assert any(r.is_self for r in page.rows)
    assert page.viewer_row is None


@pytest.mark.django_db
def test_leaderboard_views(client):
    UserFactory(honor_points=50)
    url = reverse("rewards:leaderboard")
    r = client.get(url)
    assert r.status_code == 200
    assert b"Leaderboard" in r.content or b"leaderboard" in r.content.lower()

    r2 = client.get(url, {"tab": "xp"})
    assert r2.status_code == 200
    r3 = client.get(url, {"tab": "companies"})
    assert r3.status_code == 200

    rows_url = reverse("rewards:leaderboard_rows")
    r4 = client.get(rows_url, {"tab": "reputation", "offset": 0})
    assert r4.status_code == 200


@pytest.mark.django_db
def test_top_n_cap():
    # Creating 105 users is heavier but ensures TOP_N bound
    for i in range(TOP_N + 5):
        UserFactory(honor_points=TOP_N + 5 - i, username=f"rank{i:03d}")
    # Walk pages
    seen = 0
    offset = 0
    while True:
        page = get_leaderboard(TAB_REPUTATION, offset=offset)
        seen += len(page.rows)
        if page.next_offset is None:
            break
        offset = page.next_offset
    assert seen == TOP_N
