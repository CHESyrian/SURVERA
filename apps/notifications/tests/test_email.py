"""Email channel tests – verification codes, invites, survey publish, redirect."""
import pytest
from django.conf import settings
from django.core import mail
from django.test import override_settings

from apps.accounts.verification import issue_and_send_code
from apps.factories import CompanyFactory, UserFactory
from apps.notifications.email import (
    email_survey_published,
    email_team_invite,
    resolve_recipient_email,
    send_notification_email,
    send_plain_test_email,
)
from apps.notifications.preferences import get_or_create_preferences


TEST_INBOX = "surveracorp.test@gmail.com"


@pytest.mark.django_db
class TestResolveRecipient:
    def test_no_redirect_returns_original(self, settings):
        settings.EMAIL_FOR_TEST = TEST_INBOX
        settings.EMAIL_REDIRECT_TO_TEST = False
        assert resolve_recipient_email("user@example.com") == "user@example.com"

    def test_redirect_sends_to_test_inbox(self, settings):
        settings.EMAIL_FOR_TEST = TEST_INBOX
        settings.EMAIL_REDIRECT_TO_TEST = True
        assert resolve_recipient_email("user@example.com") == TEST_INBOX


@pytest.mark.django_db
class TestPlainAndNotificationEmail:
    def test_send_plain_test_email_to_email_for_test(self, settings):
        settings.EMAIL_FOR_TEST = TEST_INBOX
        mail.outbox.clear()
        ok = send_plain_test_email(subject="SURVERA unit test")
        assert ok is True
        assert len(mail.outbox) == 1
        assert mail.outbox[0].to == [TEST_INBOX]
        assert "SURVERA unit test" in mail.outbox[0].subject

    def test_notification_email_respects_redirect(self, settings):
        settings.EMAIL_FOR_TEST = TEST_INBOX
        settings.EMAIL_REDIRECT_TO_TEST = True
        mail.outbox.clear()
        ok = send_notification_email(
            to_email="member@example.com",
            subject="SURVERA: redirected",
            template_name="notifications/email/team_invite.html",
            context={
                "user": UserFactory.build(email="member@example.com"),
                "company": CompanyFactory.build(name="Co"),
                "role_label": "Participant",
                "body": "Welcome",
                "action_url": "http://localhost:8000/companies/",
                "reactivated": False,
            },
        )
        assert ok is True
        assert len(mail.outbox) == 1
        assert mail.outbox[0].to == [TEST_INBOX]

    def test_team_invite_email(self, settings):
        settings.EMAIL_REDIRECT_TO_TEST = False
        user = UserFactory(email=TEST_INBOX)
        company = CompanyFactory(name="Invite Co")
        mail.outbox.clear()
        ok = email_team_invite(
            user=user,
            company=company,
            role_label="Moderator",
            body="You joined the team.",
            link="/companies/1/team/",
            reactivated=False,
        )
        assert ok is True
        assert len(mail.outbox) == 1
        msg = mail.outbox[0]
        assert msg.to == [TEST_INBOX]
        assert "Invite Co" in msg.subject or "Invite Co" in msg.body

    def test_survey_published_email(self, settings):
        settings.EMAIL_REDIRECT_TO_TEST = False
        user = UserFactory(email=TEST_INBOX)
        mail.outbox.clear()
        ok = email_survey_published(
            user=user,
            survey_title="Customer Feedback",
            company_name="Acme",
            body="Please take this survey.",
            link="/r/take/9/",
            points_reward=15,
        )
        assert ok is True
        assert len(mail.outbox) == 1
        msg = mail.outbox[0]
        assert msg.to == [TEST_INBOX]
        assert "Customer Feedback" in msg.subject


@pytest.mark.django_db
class TestVerificationEmail:
    def test_issue_and_send_code_delivers_to_user(self, settings):
        settings.EMAIL_REDIRECT_TO_TEST = False
        user = UserFactory(email=TEST_INBOX, is_email_verified=False)
        mail.outbox.clear()
        code, _ = issue_and_send_code(user)
        assert code is not None
        assert len(mail.outbox) == 1
        msg = mail.outbox[0]
        assert msg.to == [TEST_INBOX]
        assert code.code in msg.body

    @override_settings(EMAIL_FOR_TEST=TEST_INBOX, EMAIL_REDIRECT_TO_TEST=True)
    def test_verification_code_redirects_to_email_for_test(self):
        user = UserFactory(email="other@example.com", is_email_verified=False)
        mail.outbox.clear()
        code, _ = issue_and_send_code(user)
        assert code is not None
        assert len(mail.outbox) == 1
        assert mail.outbox[0].to == [TEST_INBOX]
        assert code.code in mail.outbox[0].body


@pytest.mark.django_db
class TestEmailPreferenceGate:
    def test_team_invite_task_respects_email_pref(self, settings):
        """When email_team_invite pref is off, task still may be called but wants_email is False."""
        from apps.notifications.preferences import wants_email
        from apps.notifications.models import Notification

        settings.EMAIL_REDIRECT_TO_TEST = False
        user = UserFactory(email=TEST_INBOX)
        prefs = get_or_create_preferences(user)
        prefs.email_team_invite = False
        prefs.save(update_fields=["email_team_invite"])
        assert wants_email(user, Notification.Type.TEAM_INVITE) is False

        prefs.email_team_invite = True
        prefs.save(update_fields=["email_team_invite"])
        assert wants_email(user, Notification.Type.TEAM_INVITE) is True
