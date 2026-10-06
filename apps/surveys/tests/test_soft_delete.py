"""Soft-deleted surveys must not appear in Discover, take, export, or analytics."""
import pytest
from django.urls import reverse

from apps.factories import QuestionFactory, ResponseFactory, SurveyFactory, UserFactory
from apps.responses.models import Response
from apps.surveys.models import Survey
from apps.surveys.services import publish_survey

BACKEND = "django.contrib.auth.backends.ModelBackend"


def _login(client, user):
    client.force_login(user, backend=BACKEND)


def _active_public_survey(company, owner):
    survey = SurveyFactory(
        company=company,
        created_by=owner,
        status=Survey.Status.DRAFT,
        visibility=Survey.Visibility.PUBLIC,
        is_paid=False,
    )
    QuestionFactory(survey=survey, order=1, text="Q1?")
    publish_survey(survey)
    survey.refresh_from_db()
    return survey


@pytest.mark.django_db
class TestSoftDeletedSurveyHidden:
    def test_soft_delete_sets_flag(self, company, owner, owner_membership):
        survey = _active_public_survey(company, owner)
        assert survey.is_deleted is False
        survey.delete()
        survey.refresh_from_db()
        assert survey.is_deleted is True
        # Default manager excludes soft-deleted rows
        assert not Survey.objects.filter(pk=survey.pk).exists()
        assert Survey.all_objects.filter(pk=survey.pk, is_deleted=True).exists()

    def test_discover_excludes_soft_deleted(
        self, client, company, owner, owner_membership
    ):
        survey = _active_public_survey(company, owner)
        url = reverse("surveys:discover")
        response = client.get(url)
        assert response.status_code == 200
        assert survey.title.encode() in response.content

        survey.delete()
        response = client.get(url)
        assert response.status_code == 200
        assert survey.title.encode() not in response.content

    def test_take_returns_404_for_soft_deleted(
        self, client, company, owner, owner_membership, person
    ):
        survey = _active_public_survey(company, owner)
        _login(client, person)
        url = reverse("responses:take", kwargs={"pk": survey.pk})
        assert client.get(url).status_code == 200

        survey.delete()
        assert client.get(url).status_code == 404

    def test_export_returns_404_for_soft_deleted_even_for_manager(
        self, client, company, owner, owner_membership
    ):
        survey = _active_public_survey(company, owner)
        _login(client, owner)
        url = reverse("responses:export_csv", kwargs={"pk": survey.pk})
        assert client.get(url).status_code == 200

        survey.delete()
        assert client.get(url).status_code == 404

    def test_response_list_returns_404_for_soft_deleted(
        self, client, company, owner, owner_membership
    ):
        survey = _active_public_survey(company, owner)
        _login(client, owner)
        url = reverse("responses:list", kwargs={"pk": survey.pk})
        assert client.get(url).status_code == 200

        survey.delete()
        assert client.get(url).status_code == 404

    def test_analytics_returns_404_for_soft_deleted(
        self, client, company, owner, owner_membership
    ):
        survey = _active_public_survey(company, owner)
        _login(client, owner)
        url = reverse("surveys:analytics", kwargs={"pk": survey.pk})
        assert client.get(url).status_code == 200

        survey.delete()
        assert client.get(url).status_code == 404

    def test_cannot_publish_soft_deleted(self, company, owner, owner_membership):
        survey = SurveyFactory(
            company=company,
            created_by=owner,
            status=Survey.Status.DRAFT,
        )
        QuestionFactory(survey=survey)
        survey.delete()
        # Reload via all_objects for service call
        deleted = Survey.all_objects.get(pk=survey.pk)
        with pytest.raises(ValueError, match="deleted"):
            publish_survey(deleted)
