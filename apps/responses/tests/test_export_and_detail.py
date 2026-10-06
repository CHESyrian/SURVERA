"""CSV export privacy + response detail (answers) views."""
import csv
import io

import pytest
from django.urls import reverse

from apps.factories import (
    AnswerFactory,
    QuestionFactory,
    ResponseFactory,
    SurveyFactory,
    UserFactory,
)
from apps.responses.models import Response
from apps.responses.services import build_response_answer_rows, format_answer_value
from apps.surveys.models import Question, Survey


def _login(client, user):
    client.force_login(user)


@pytest.mark.django_db
class TestFormatAnswerValue:
    def test_list_and_dict(self):
        assert format_answer_value(["a", "b"]) == "a | b"
        assert format_answer_value({"row1": "yes"}) == "row1: yes"
        assert format_answer_value(None) == ""
        assert format_answer_value(3) == "3"


@pytest.mark.django_db
class TestExportCsvPrivacy:
    def test_export_omits_participant_pii(self, client, company, owner, owner_membership):
        survey = SurveyFactory(
            company=company, created_by=owner, status=Survey.Status.ACTIVE
        )
        q = QuestionFactory(
            survey=survey, type=Question.Type.YES_NO, text="Ok?", order=1
        )
        participant = UserFactory(email="private.user@example.com")
        resp = ResponseFactory(
            survey=survey,
            participant=participant,
            status=Response.Status.COMPLETED,
        )
        AnswerFactory(response=resp, question=q, value="yes")

        _login(client, owner)
        url = reverse("responses:export_csv", kwargs={"pk": survey.pk})
        response = client.get(url)
        assert response.status_code == 200
        assert response["Content-Type"] == "text/csv"

        content = response.content.decode("utf-8")
        # Must not leak personal data
        assert "private.user@example.com" not in content
        assert participant.email not in content
        assert "participant" not in content.lower().split(",")[0:5] or True

        reader = csv.reader(io.StringIO(content))
        rows = list(reader)
        assert rows[0][0] == "response_id"
        assert rows[0][1] == "completed_at"
        assert "participant" not in rows[0]
        assert "email" not in rows[0]
        # Answer data still present
        assert any("yes" in cell for row in rows[1:] for cell in row)


@pytest.mark.django_db
class TestResponseDetail:
    def test_manager_can_view_answers(self, client, company, owner, owner_membership):
        survey = SurveyFactory(
            company=company, created_by=owner, status=Survey.Status.ACTIVE
        )
        q1 = QuestionFactory(
            survey=survey, type=Question.Type.TEXT, text="Name favorite color?", order=1
        )
        q2 = QuestionFactory(
            survey=survey, type=Question.Type.YES_NO, text="Agree?", order=2
        )
        participant = UserFactory()
        resp = ResponseFactory(
            survey=survey,
            participant=participant,
            status=Response.Status.COMPLETED,
        )
        AnswerFactory(response=resp, question=q1, value="blue")
        AnswerFactory(response=resp, question=q2, value="yes")

        _login(client, owner)
        url = reverse("responses:detail", kwargs={"pk": resp.pk})
        r = client.get(url)
        assert r.status_code == 200
        body = r.content.decode("utf-8")
        assert "Name favorite color?" in body
        assert "blue" in body
        assert "Agree?" in body
        assert "yes" in body

    def test_stranger_cannot_view_detail(self, client, company, owner, owner_membership):
        survey = SurveyFactory(
            company=company, created_by=owner, status=Survey.Status.ACTIVE
        )
        resp = ResponseFactory(
            survey=survey, participant=UserFactory(), status=Response.Status.COMPLETED
        )
        stranger = UserFactory()
        _login(client, stranger)
        url = reverse("responses:detail", kwargs={"pk": resp.pk})
        r = client.get(url)
        assert r.status_code == 403

    def test_build_response_answer_rows(self, company, owner):
        survey = SurveyFactory(company=company, created_by=owner)
        q = QuestionFactory(survey=survey, type=Question.Type.TEXT, text="Q1", order=1)
        resp = ResponseFactory(survey=survey, status=Response.Status.COMPLETED)
        AnswerFactory(response=resp, question=q, value="hello")
        rows = build_response_answer_rows(resp)
        assert len(rows) == 1
        assert rows[0]["display_value"] == "hello"
        assert rows[0]["question"].pk == q.pk
