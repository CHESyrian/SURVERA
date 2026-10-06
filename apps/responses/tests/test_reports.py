"""Company manager can file reports; ACL enforced."""
import pytest
from django.urls import reverse

from apps.factories import (
    ResponseFactory,
    SurveyFactory,
    UserFactory,
)
from apps.responses.models import Report, Response
from apps.surveys.models import Survey

BACKEND = "django.contrib.auth.backends.ModelBackend"


def _login(client, user):
    client.force_login(user, backend=BACKEND)


@pytest.mark.django_db
class TestReportFlow:
    def test_manager_can_submit_report(
        self, client, company, owner, owner_membership
    ):
        participant = UserFactory()
        survey = SurveyFactory(company=company, created_by=owner, status=Survey.Status.ACTIVE)
        response = ResponseFactory(
            survey=survey, participant=participant, status=Response.Status.COMPLETED
        )
        _login(client, owner)
        url = reverse("responses:report", kwargs={"pk": response.pk})
        r = client.get(url)
        assert r.status_code == 200
        r = client.post(
            url,
            {"type": Report.Type.SPAM, "note": "Looks automated."},
        )
        assert r.status_code == 302
        assert Report.objects.filter(response=response, reporter=owner).exists()
        report = Report.objects.get(response=response)
        assert report.status == Report.Status.PENDING
        assert report.company_id == company.pk

    def test_stranger_cannot_report(self, client, company, owner, owner_membership):
        participant = UserFactory()
        survey = SurveyFactory(company=company, created_by=owner, status=Survey.Status.ACTIVE)
        response = ResponseFactory(
            survey=survey, participant=participant, status=Response.Status.COMPLETED
        )
        stranger = UserFactory()
        _login(client, stranger)
        url = reverse("responses:report", kwargs={"pk": response.pk})
        assert client.get(url).status_code == 403
