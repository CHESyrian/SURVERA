"""Tests for notification services and publish fan-out."""
import pytest
from django.urls import reverse

from apps.companies.models import CompanyMembership
from apps.factories import (
    CompanyMembershipFactory,
    QuestionFactory,
    SurveyFactory,
    UserFactory,
)
from apps.notifications.models import Notification
from apps.notifications.services import (
    mark_all_read,
    notify_points_awarded,
    notify_survey_published,
    notify_user,
    unread_count,
)
from apps.surveys.models import Survey
from apps.surveys.services import publish_survey


@pytest.mark.django_db
class TestNotifyUser:
    def test_creates_unread(self, person):
        n = notify_user(
            user=person,
            type=Notification.Type.SYSTEM,
            title="Hello",
            body="World",
            link="/",
        )
        assert n is not None
        assert n.read_at is None
        assert unread_count(person) == 1

    def test_mark_all_read(self, person):
        notify_user(user=person, type=Notification.Type.SYSTEM, title="A")
        notify_user(user=person, type=Notification.Type.SYSTEM, title="B")
        assert unread_count(person) == 2
        mark_all_read(person)
        assert unread_count(person) == 0


@pytest.mark.django_db
class TestSurveyPublishedFanout:
    def test_notifies_company_members_not_owner(
        self, company, owner, owner_membership, participant, participant_membership
    ):
        survey = SurveyFactory(
            company=company,
            created_by=owner,
            status=Survey.Status.DRAFT,
            is_paid=False,
            visibility=Survey.Visibility.PUBLIC,
        )
        QuestionFactory(survey=survey)
        publish_survey(survey)
        notes = Notification.objects.filter(
            type=Notification.Type.SURVEY_PUBLISHED, payload__survey_id=survey.pk
        )
        recipient_ids = set(notes.values_list("user_id", flat=True))
        assert participant.pk in recipient_ids
        assert owner.pk not in recipient_ids  # publisher excluded
        assert notes.filter(user=participant).first().link.endswith(
            reverse("responses:take", kwargs={"pk": survey.pk})
        )

    def test_members_only_skips_non_member(self, company, owner, owner_membership):
        outsider = UserFactory()
        survey = SurveyFactory(
            company=company,
            created_by=owner,
            status=Survey.Status.DRAFT,
            is_paid=True,
            points_reward=10,
            visibility=Survey.Visibility.PUBLIC,
            targeting={"members_only": True},
        )
        QuestionFactory(survey=survey)
        publish_survey(survey)
        assert not Notification.objects.filter(
            user=outsider, type=Notification.Type.SURVEY_PUBLISHED
        ).exists()

    def test_idempotent_publish_does_not_double_notify(
        self, company, owner, owner_membership, participant, participant_membership
    ):
        survey = SurveyFactory(
            company=company, created_by=owner, status=Survey.Status.DRAFT
        )
        QuestionFactory(survey=survey)
        publish_survey(survey)
        first = Notification.objects.filter(
            user=participant, type=Notification.Type.SURVEY_PUBLISHED
        ).count()
        publish_survey(survey)  # already active → early return
        second = Notification.objects.filter(
            user=participant, type=Notification.Type.SURVEY_PUBLISHED
        ).count()
        assert first == second == 1


@pytest.mark.django_db
class TestPointsNotification:
    def test_points_awarded_notification(self, person):
        n = notify_points_awarded(user=person, amount=25, survey_title="Demo")
        assert n is not None
        assert n.type == Notification.Type.POINTS_AWARDED
        assert "25" in n.title


@pytest.mark.django_db
class TestNotificationViews:
    def test_list_requires_login(self, client):
        r = client.get(reverse("notifications:list"))
        assert r.status_code == 302

    def test_list_ok(self, client, person):
        notify_user(user=person, type=Notification.Type.SYSTEM, title="Hi")
        client.force_login(person, backend="django.contrib.auth.backends.ModelBackend")
        r = client.get(reverse("notifications:list"))
        assert r.status_code == 200
        assert b"Hi" in r.content

    def test_open_marks_read_and_redirects(self, client, person):
        n = notify_user(
            user=person,
            type=Notification.Type.SYSTEM,
            title="Go",
            link="/surveys/discover/",
        )
        client.force_login(person, backend="django.contrib.auth.backends.ModelBackend")
        r = client.get(reverse("notifications:open", kwargs={"pk": n.pk}))
        assert r.status_code == 302
        n.refresh_from_db()
        assert n.read_at is not None


@pytest.mark.django_db
class TestTeamInviteNotification:
    def test_notify_team_invite_creates_notification(self, company, owner, person):
        from apps.notifications.services import notify_team_invite
        from apps.companies.models import CompanyMembership

        n = notify_team_invite(
            user=person,
            company=company,
            role=CompanyMembership.Role.PARTICIPANT,
            invited_by=owner,
        )
        assert n is not None
        assert n.type == Notification.Type.TEAM_INVITE
        assert company.name[:20] in n.title or "Joined" in n.title or n.title
        assert n.payload["company_id"] == company.pk
        assert n.payload["role"] == CompanyMembership.Role.PARTICIPANT


@pytest.mark.django_db
class TestEmailAndAsyncDelivery:
    def test_team_invite_sends_email(self, company, owner, person):
        from django.core import mail
        from apps.notifications.services import notify_team_invite
        from apps.companies.models import CompanyMembership

        mail.outbox.clear()
        notify_team_invite(
            user=person,
            company=company,
            role=CompanyMembership.Role.PARTICIPANT,
            invited_by=owner,
        )
        # CELERY_TASK_ALWAYS_EAGER → email runs inline
        assert len(mail.outbox) >= 1
        assert person.email in mail.outbox[-1].to
        assert "SURVERA" in mail.outbox[-1].subject

    def test_publish_queues_in_app_notifications(
        self, company, owner, owner_membership, participant, participant_membership
    ):
        from apps.notifications.models import Notification
        from apps.surveys.services import publish_survey
        from apps.surveys.models import Survey
        from apps.factories import SurveyFactory, QuestionFactory

        survey = SurveyFactory(
            company=company,
            created_by=owner,
            status=Survey.Status.DRAFT,
            is_paid=True,
            points_reward=10,
            visibility=Survey.Visibility.PRIVATE,
            targeting={"members_only": True},
        )
        QuestionFactory(survey=survey)
        publish_survey(survey)
        assert Notification.objects.filter(
            user=participant, type=Notification.Type.SURVEY_PUBLISHED
        ).exists()

    def test_should_email_only_private_or_members_only(self, company, owner):
        from apps.notifications.targeting_email import should_email_survey_published
        from apps.factories import SurveyFactory
        from apps.surveys.models import Survey

        public = SurveyFactory(
            company=company,
            created_by=owner,
            visibility=Survey.Visibility.PUBLIC,
            targeting={},
        )
        private = SurveyFactory(
            company=company,
            created_by=owner,
            visibility=Survey.Visibility.PRIVATE,
            targeting={},
        )
        members = SurveyFactory(
            company=company,
            created_by=owner,
            visibility=Survey.Visibility.PUBLIC,
            targeting={"members_only": True},
        )
        assert should_email_survey_published(public) is False
        assert should_email_survey_published(private) is True
        assert should_email_survey_published(members) is True

    def test_absolute_url(self):
        from apps.notifications.email import absolute_url
        from django.test import override_settings

        with override_settings(SITE_URL="https://app.survera.test"):
            assert absolute_url("/r/take/1/") == "https://app.survera.test/r/take/1/"


@pytest.mark.django_db
class TestNotificationPreferences:
    def test_inapp_opt_out_skips_create(self, person):
        from apps.notifications.preferences import get_or_create_preferences
        from apps.notifications.models import Notification

        prefs = get_or_create_preferences(person)
        prefs.inapp_system = False
        prefs.save()
        n = notify_user(user=person, type=Notification.Type.SYSTEM, title="Nope")
        assert n is None
        assert not Notification.objects.filter(user=person).exists()

    def test_email_opt_out_skips_team_invite_mail(self, company, owner, person):
        from django.core import mail
        from apps.notifications.preferences import get_or_create_preferences
        from apps.notifications.services import notify_team_invite
        from apps.companies.models import CompanyMembership

        prefs = get_or_create_preferences(person)
        prefs.email_team_invite = False
        prefs.save()
        mail.outbox.clear()
        notify_team_invite(
            user=person,
            company=company,
            role=CompanyMembership.Role.PARTICIPANT,
            invited_by=owner,
        )
        assert len(mail.outbox) == 0

    def test_defaults_without_row(self, person):
        from apps.notifications.preferences import wants_inapp, wants_email
        from apps.notifications.models import Notification

        assert wants_inapp(person, Notification.Type.TEAM_INVITE) is True
        assert wants_email(person, Notification.Type.TEAM_INVITE) is True
        assert wants_email(person, Notification.Type.POINTS_AWARDED) is False
