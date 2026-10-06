"""Email digest service tests."""
import pytest
from django.core import mail
from django.utils import timezone

from apps.factories import UserFactory
from apps.notifications.digests import (
    collect_digest_items,
    run_digests,
    send_digest_for_user,
)
from apps.notifications.models import Notification
from apps.notifications.preferences import NotificationPreference, get_or_create_preferences


@pytest.mark.django_db
def test_send_digest_with_unread():
    user = UserFactory(email="digest@example.com")
    prefs = get_or_create_preferences(user)
    prefs.email_digest = NotificationPreference.DigestFrequency.DAILY
    prefs.save(update_fields=["email_digest"])
    Notification.objects.create(
        user=user,
        type=Notification.Type.SYSTEM,
        title="Hello",
        body="World",
    )
    assert send_digest_for_user(user) is True
    assert len(mail.outbox) == 1
    assert "digest" in mail.outbox[0].subject.lower() or "unread" in mail.outbox[0].subject.lower()
    prefs.refresh_from_db()
    assert prefs.last_digest_sent_at is not None


@pytest.mark.django_db
def test_no_digest_when_no_unread():
    user = UserFactory(email="empty@example.com")
    get_or_create_preferences(user)
    assert send_digest_for_user(user) is False
    assert len(mail.outbox) == 0


@pytest.mark.django_db
def test_digest_off_skips():
    user = UserFactory(email="off@example.com")
    prefs = get_or_create_preferences(user)
    prefs.email_digest = NotificationPreference.DigestFrequency.OFF
    prefs.save(update_fields=["email_digest"])
    Notification.objects.create(
        user=user,
        type=Notification.Type.SYSTEM,
        title="X",
        body="Y",
    )
    assert send_digest_for_user(user) is False
    assert len(mail.outbox) == 0


@pytest.mark.django_db
def test_run_digests_daily_batch():
    u1 = UserFactory(email="a@example.com")
    u2 = UserFactory(email="b@example.com")
    for u in (u1, u2):
        p = get_or_create_preferences(u)
        p.email_digest = NotificationPreference.DigestFrequency.DAILY
        p.save(update_fields=["email_digest"])
        Notification.objects.create(user=u, type=Notification.Type.SYSTEM, title="T", body="B")
    sent = run_digests(frequency=NotificationPreference.DigestFrequency.DAILY)
    assert sent == 2
    assert len(mail.outbox) == 2


@pytest.mark.django_db
def test_collect_digest_items_only_unread():
    user = UserFactory()
    Notification.objects.create(user=user, type=Notification.Type.SYSTEM, title="U", body="")
    n = Notification.objects.create(user=user, type=Notification.Type.SYSTEM, title="R", body="")
    n.read_at = timezone.now()
    n.save(update_fields=["read_at"])
    items = collect_digest_items(user)
    assert len(items) == 1
    assert items[0].title == "U"
