"""View-level permission tests for edit, publish, export, response list."""
import pytest
from django.urls import reverse

from apps.factories import QuestionFactory, SurveyFactory, UserFactory
from apps.surveys.models import Survey
from apps.surveys.services import freeze_survey, publish_survey

BACKEND = "django.contrib.auth.backends.ModelBackend"


def _login(client, user):
    client.force_login(user, backend=BACKEND)
    assert client.session.get("_auth_user_id") == str(user.pk)


@pytest.mark.django_db
class TestEditRequiresManager:
    def test_participant_cannot_edit(
        self, client, company, owner, owner_membership, participant, participant_membership
    ):
        survey = SurveyFactory(company=company, created_by=owner, status=Survey.Status.DRAFT)
        _login(client, participant)
        url = reverse("surveys:edit", kwargs={"pk": survey.pk})
        response = client.get(url)
        assert response.status_code == 403

    def test_owner_can_edit_draft(self, client, company, owner, owner_membership):
        survey = SurveyFactory(company=company, created_by=owner, status=Survey.Status.DRAFT)
        _login(client, owner)
        url = reverse("surveys:edit", kwargs={"pk": survey.pk})
        response = client.get(url)
        assert response.status_code == 200

    def test_moderator_can_edit_draft(
        self, client, company, owner, moderator, moderator_membership
    ):
        survey = SurveyFactory(company=company, created_by=owner, status=Survey.Status.DRAFT)
        _login(client, moderator)
        url = reverse("surveys:edit", kwargs={"pk": survey.pk})
        response = client.get(url)
        assert response.status_code == 200

    def test_stranger_cannot_edit(self, client, company, owner, owner_membership):
        survey = SurveyFactory(company=company, created_by=owner, status=Survey.Status.DRAFT)
        stranger = UserFactory()
        _login(client, stranger)
        url = reverse("surveys:edit", kwargs={"pk": survey.pk})
        response = client.get(url)
        assert response.status_code == 403


@pytest.mark.django_db
class TestFrozenBlocksEdit:
    def test_edit_redirects_when_frozen(self, client, company, owner, owner_membership):
        survey = SurveyFactory(company=company, created_by=owner, status=Survey.Status.DRAFT)
        QuestionFactory(survey=survey)
        freeze_survey(survey)
        _login(client, owner)
        url = reverse("surveys:edit", kwargs={"pk": survey.pk})
        response = client.get(url)
        assert response.status_code == 302
        assert response.url == reverse("surveys:detail", kwargs={"pk": survey.pk})

    def test_edit_redirects_when_active(self, client, company, owner, owner_membership):
        survey = SurveyFactory(company=company, created_by=owner, status=Survey.Status.DRAFT)
        QuestionFactory(survey=survey)
        publish_survey(survey)
        _login(client, owner)
        url = reverse("surveys:edit", kwargs={"pk": survey.pk})
        response = client.get(url)
        assert response.status_code == 302
        assert response.url == reverse("surveys:detail", kwargs={"pk": survey.pk})

    def test_question_create_blocked_when_frozen(self, client, company, owner, owner_membership):
        survey = SurveyFactory(company=company, created_by=owner, status=Survey.Status.DRAFT)
        QuestionFactory(survey=survey)
        freeze_survey(survey)
        _login(client, owner)
        url = reverse("surveys:question_create", kwargs={"survey_pk": survey.pk})
        response = client.get(url)
        assert response.status_code == 302
        assert response.url == reverse("surveys:detail", kwargs={"pk": survey.pk})


@pytest.mark.django_db
class TestPublishRequiresManager:
    def test_participant_cannot_publish(
        self, client, company, owner, owner_membership, participant, participant_membership
    ):
        survey = SurveyFactory(company=company, created_by=owner, status=Survey.Status.DRAFT)
        QuestionFactory(survey=survey)
        _login(client, participant)
        url = reverse("surveys:publish", kwargs={"pk": survey.pk})
        response = client.post(url)
        assert response.status_code == 403

    def test_owner_can_publish(self, client, company, owner, owner_membership):
        survey = SurveyFactory(company=company, created_by=owner, status=Survey.Status.DRAFT)
        QuestionFactory(survey=survey)
        _login(client, owner)
        url = reverse("surveys:publish", kwargs={"pk": survey.pk})
        response = client.post(url)
        assert response.status_code == 302
        survey.refresh_from_db()
        assert survey.status == Survey.Status.ACTIVE


@pytest.mark.django_db
class TestExportRestrictedToManagers:
    def test_participant_cannot_export(
        self, client, company, owner, owner_membership, participant, participant_membership
    ):
        survey = SurveyFactory(company=company, created_by=owner, status=Survey.Status.ACTIVE)
        _login(client, participant)
        url = reverse("responses:export_csv", kwargs={"pk": survey.pk})
        response = client.get(url)
        assert response.status_code == 403

    def test_owner_can_export(self, client, company, owner, owner_membership):
        survey = SurveyFactory(company=company, created_by=owner, status=Survey.Status.ACTIVE)
        _login(client, owner)
        url = reverse("responses:export_csv", kwargs={"pk": survey.pk})
        response = client.get(url)
        assert response.status_code == 200
        assert response["Content-Type"] == "text/csv"

    def test_moderator_can_export(
        self, client, company, owner, moderator, moderator_membership
    ):
        survey = SurveyFactory(company=company, created_by=owner, status=Survey.Status.ACTIVE)
        _login(client, moderator)
        url = reverse("responses:export_csv", kwargs={"pk": survey.pk})
        response = client.get(url)
        assert response.status_code == 200

    def test_stranger_cannot_export(self, client, company, owner, owner_membership):
        survey = SurveyFactory(company=company, created_by=owner, status=Survey.Status.ACTIVE)
        stranger = UserFactory()
        _login(client, stranger)
        url = reverse("responses:export_csv", kwargs={"pk": survey.pk})
        response = client.get(url)
        assert response.status_code == 403

    def test_participant_cannot_view_response_list(
        self, client, company, owner, owner_membership, participant, participant_membership
    ):
        survey = SurveyFactory(company=company, created_by=owner, status=Survey.Status.ACTIVE)
        _login(client, participant)
        url = reverse("responses:list", kwargs={"pk": survey.pk})
        response = client.get(url)
        assert response.status_code == 403

    def test_superuser_can_export(self, client, company, owner, owner_membership):
        survey = SurveyFactory(company=company, created_by=owner, status=Survey.Status.ACTIVE)
        su = UserFactory(is_superuser=True, is_staff=True)
        _login(client, su)
        url = reverse("responses:export_csv", kwargs={"pk": survey.pk})
        response = client.get(url)
        assert response.status_code == 200


@pytest.mark.django_db
class TestCreateSurveyPermissions:
    def test_person_without_company_cannot_create(self, client, person):
        _login(client, person)
        url = reverse("surveys:create")
        response = client.get(url)
        assert response.status_code == 302
        assert response.url == reverse("surveys:list")

    def test_owner_can_open_create(self, client, owner, company, owner_membership):
        _login(client, owner)
        url = reverse("surveys:create")
        response = client.get(url)
        assert response.status_code == 200
