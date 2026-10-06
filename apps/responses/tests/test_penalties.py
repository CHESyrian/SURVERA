"""Report penalty catalog: warnings ladder, honor, rank, freeze, close."""
from datetime import timedelta

import pytest
from django.core import mail
from django.utils import timezone

from apps.accounts.honor import apply_honor_delta
from apps.accounts.models import HonorEvent
from apps.factories import (
    AnswerFactory,
    QuestionFactory,
    ResponseFactory,
    SurveyFactory,
    UserFactory,
)
from apps.notifications.models import Notification
from apps.responses.models import Report, Response
from apps.responses.penalties import (
    WARNING_1_HONOR,
    WARNING_2_HONOR,
    dismiss_report,
    resolve_with_penalty,
)
from apps.surveys.models import Question, Survey


def _make_report(company, owner, participant, honor=500):
    apply_honor_delta(
        user=participant,
        amount=honor,
        reason=HonorEvent.Reason.ADMIN_ADJUST,
        note="seed",
    )
    participant.refresh_from_db()
    survey = SurveyFactory(
        company=company, created_by=owner, status=Survey.Status.ACTIVE
    )
    q = QuestionFactory(survey=survey, type=Question.Type.YES_NO, text="Ok?")
    response = ResponseFactory(
        survey=survey, participant=participant, status=Response.Status.COMPLETED
    )
    AnswerFactory(response=response, question=q, value="yes")
    report = Report.objects.create(
        reporter=owner,
        company=company,
        survey=survey,
        response=response,
        reported_user=participant,
        type=Report.Type.SPAM,
        note="Issue",
        status=Report.Status.PENDING,
    )
    return report


@pytest.mark.django_db
class TestWarningLadder:
    def test_first_warning_deducts_100_honor(self, company, owner):
        participant = UserFactory()
        report = _make_report(company, owner, participant, honor=250)
        honor0 = participant.honor_points
        resolve_with_penalty(
            report=report,
            admin_user=owner,
            penalty_kind=Report.PenaltyKind.WARNING,
            resolution_note="First warning",
        )
        participant.refresh_from_db()
        report.refresh_from_db()
        assert participant.warning_count == 1
        assert participant.honor_points == honor0 - WARNING_1_HONOR
        assert report.warning_number == 1
        assert Notification.objects.filter(user=participant).exists()
        assert len(mail.outbox) >= 2

    def test_second_warning_deducts_200_honor(self, company, owner):
        participant = UserFactory(warning_count=1)
        report = _make_report(company, owner, participant, honor=400)
        honor0 = participant.honor_points
        resolve_with_penalty(
            report=report,
            admin_user=owner,
            penalty_kind=Report.PenaltyKind.WARNING,
        )
        participant.refresh_from_db()
        assert participant.warning_count == 2
        assert participant.honor_points == honor0 - WARNING_2_HONOR

    def test_third_warning_freezes_one_week(self, company, owner):
        participant = UserFactory(warning_count=2)
        report = _make_report(company, owner, participant)
        resolve_with_penalty(
            report=report,
            admin_user=owner,
            penalty_kind=Report.PenaltyKind.WARNING,
        )
        participant.refresh_from_db()
        assert participant.warning_count == 3
        assert participant.frozen_until is not None
        assert participant.frozen_until > timezone.now() + timedelta(days=6)

    def test_fifth_warning_closes_account(self, company, owner):
        participant = UserFactory(warning_count=4)
        report = _make_report(company, owner, participant)
        resolve_with_penalty(
            report=report,
            admin_user=owner,
            penalty_kind=Report.PenaltyKind.WARNING,
        )
        participant.refresh_from_db()
        assert participant.warning_count == 5
        assert participant.closed_at is not None
        assert participant.is_active is False
        assert participant.is_permanently_closed


@pytest.mark.django_db
class TestOtherPenalties:
    def test_honor_deduction_admin_amount(self, company, owner):
        participant = UserFactory()
        report = _make_report(company, owner, participant, honor=300)
        honor0 = participant.honor_points
        resolve_with_penalty(
            report=report,
            admin_user=owner,
            penalty_kind=Report.PenaltyKind.HONOR_DEDUCTION,
            penalty_reputation=75,
        )
        participant.refresh_from_db()
        assert participant.honor_points == honor0 - 75

    def test_rank_reduction(self, company, owner):
        participant = UserFactory()
        report = _make_report(company, owner, participant, honor=250)
        participant.refresh_from_db()
        level0 = participant.trust_level
        assert level0 >= 2
        resolve_with_penalty(
            report=report,
            admin_user=owner,
            penalty_kind=Report.PenaltyKind.RANK_REDUCTION,
            penalty_rank_levels=1,
        )
        participant.refresh_from_db()
        assert participant.trust_level == level0 - 1

    def test_account_freeze_admin_days(self, company, owner):
        participant = UserFactory()
        report = _make_report(company, owner, participant)
        resolve_with_penalty(
            report=report,
            admin_user=owner,
            penalty_kind=Report.PenaltyKind.ACCOUNT_FREEZE,
            penalty_freeze_days=14,
        )
        participant.refresh_from_db()
        assert participant.frozen_until is not None
        assert participant.frozen_until > timezone.now() + timedelta(days=13)

    def test_account_closure(self, company, owner):
        participant = UserFactory()
        report = _make_report(company, owner, participant)
        resolve_with_penalty(
            report=report,
            admin_user=owner,
            penalty_kind=Report.PenaltyKind.ACCOUNT_CLOSURE,
        )
        participant.refresh_from_db()
        assert participant.closed_at is not None
        assert not participant.is_active

    def test_dismiss_no_side_effects(self, company, owner):
        participant = UserFactory()
        report = _make_report(company, owner, participant, honor=100)
        honor0 = participant.honor_points
        dismiss_report(report=report, admin_user=owner, resolution_note="No evidence")
        participant.refresh_from_db()
        report.refresh_from_db()
        assert report.status == Report.Status.DISMISSED
        assert participant.honor_points == honor0
        assert participant.warning_count == 0
