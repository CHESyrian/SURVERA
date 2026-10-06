"""Email verification by code + resend rate limits."""
import pytest
from django.core import mail
from django.urls import reverse
from django.utils import timezone

from apps.accounts.verification import (
    RESEND_COOLDOWN_SECONDS,
    can_resend_code,
    create_verification_code,
    issue_and_send_code,
    mark_email_verified,
    verify_code,
)
from apps.factories import UserFactory


@pytest.mark.django_db
class TestEmailVerification:
    def test_create_and_verify_code(self):
        user = UserFactory(is_email_verified=False)
        code = create_verification_code(user)
        assert len(code.code) == 6
        assert code.code.isdigit()
        assert code.is_valid

        ok, msg = verify_code(user, code.code)
        assert ok is True
        user.refresh_from_db()
        assert user.is_email_verified is True

        # Reuse blocked
        ok2, _ = verify_code(user, code.code)
        assert ok2 is False

    def test_expired_code_rejected(self):
        user = UserFactory(is_email_verified=False)
        code = create_verification_code(user)
        code.expires_at = timezone.now() - timezone.timedelta(minutes=1)
        code.save(update_fields=["expires_at"])
        ok, _ = verify_code(user, code.code)
        assert ok is False
        user.refresh_from_db()
        assert user.is_email_verified is False

    def test_issue_and_send_code_sends_email(self, settings):
        settings.EMAIL_REDIRECT_TO_TEST = False
        user = UserFactory(email="surveracorp.test@gmail.com", is_email_verified=False)
        mail.outbox.clear()
        code, msg = issue_and_send_code(user)
        assert code is not None
        assert len(mail.outbox) == 1
        assert mail.outbox[0].to == ["surveracorp.test@gmail.com"]
        assert code.code in mail.outbox[0].body

    def test_resend_rate_limited(self, settings):
        settings.EMAIL_REDIRECT_TO_TEST = False
        user = UserFactory(is_email_verified=False)
        code1, _ = issue_and_send_code(user)
        assert code1 is not None
        allowed, wait = can_resend_code(user)
        assert allowed is False
        assert wait > 0
        assert wait <= RESEND_COOLDOWN_SECONDS

        code2, msg = issue_and_send_code(user)
        assert code2 is None
        assert str(wait) in msg or "wait" in msg.lower() or "seconds" in msg.lower()

    def test_resend_bypass_rate_limit(self, settings):
        settings.EMAIL_REDIRECT_TO_TEST = False
        user = UserFactory(is_email_verified=False)
        issue_and_send_code(user)
        mail.outbox.clear()
        code, _ = issue_and_send_code(user, bypass_rate_limit=True)
        assert code is not None
        assert len(mail.outbox) == 1

    def test_mark_email_verified_helper(self):
        user = UserFactory(is_email_verified=False)
        create_verification_code(user)
        mark_email_verified(user)
        user.refresh_from_db()
        assert user.is_email_verified is True

    def test_register_redirects_to_verify(self, client):
        url = reverse("accounts:register")
        resp = client.post(
            url,
            {
                "email": "newbie@example.com",
                "username": "newbie",
                "password1": "Str0ng!Pass99",
                "password2": "Str0ng!Pass99",
            },
        )
        assert resp.status_code == 302
        assert resp.url == reverse("accounts:verify_email")

    def test_resend_view_rate_limited(self, client, settings):
        settings.EMAIL_REDIRECT_TO_TEST = False
        user = UserFactory(is_email_verified=False, password="pass12345")
        client.force_login(user)
        issue_and_send_code(user)
        resp = client.post(reverse("accounts:resend_verification"))
        assert resp.status_code == 302
        # Still only one email from initial issue (resend blocked)
        # (register tests aside — this user only got the one from issue_and_send_code)
        assert len(mail.outbox) == 1

    def test_unverified_blocked_from_company_create(self, client):
        user = UserFactory(is_email_verified=False, password="pass12345")
        client.force_login(user)
        resp = client.get(reverse("companies:create"))
        assert resp.status_code == 302
        assert reverse("accounts:verify_email") in resp.url

    def test_verified_can_open_company_create(self, client):
        user = UserFactory(is_email_verified=True, password="pass12345")
        client.force_login(user)
        resp = client.get(reverse("companies:create"))
        assert resp.status_code == 200

    def test_superuser_create_is_email_verified(self):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        user = User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="pass12345",
        )
        assert user.is_superuser is True
        assert user.is_email_verified is True

    def test_superuser_skips_verification_gate(self, client):
        from apps.accounts.decorators import user_email_verified

        user = UserFactory(
            is_email_verified=False,
            is_superuser=True,
            is_staff=True,
            password="pass12345",
        )
        # Factory may not re-run pre_save flags if set after — reload
        user.refresh_from_db()
        # Promoting to superuser via save should force verified
        if not user.is_email_verified:
            user.is_superuser = True
            user.save()
            user.refresh_from_db()
        assert user.is_email_verified is True
        assert user_email_verified(user) is True
        client.force_login(user)
        resp = client.get(reverse("companies:create"))
        assert resp.status_code == 200


@pytest.mark.django_db
class TestNotificationPrefDefaults:
    def test_email_defaults_matrix(self):
        from apps.notifications.models import Notification
        from apps.notifications.preferences import wants_email

        user = UserFactory(email="prefs@example.com")
        assert wants_email(user, Notification.Type.SURVEY_PUBLISHED) is True
        assert wants_email(user, Notification.Type.TEAM_INVITE) is True
        assert wants_email(user, Notification.Type.POINTS_AWARDED) is False
        assert wants_email(user, Notification.Type.SYSTEM) is False
