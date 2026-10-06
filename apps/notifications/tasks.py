"""Celery tasks for notification fan-out and email delivery."""
from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    name="notifications.notify_survey_published",
    max_retries=3,
    default_retry_delay=30,
)
def task_notify_survey_published(self, survey_id: int) -> int:
    """
    Async fan-out when a survey is published.

    Creates in-app notifications for eligible company members.
    Sends email only for private or members_only surveys (smaller, high-intent audiences).
    """
    try:
        from apps.surveys.models import Survey

        from .email import email_survey_published
        from .services import notify_survey_published
        from .targeting_email import should_email_survey_published

        survey = (
            Survey.objects.select_related("company")
            .filter(pk=survey_id, is_deleted=False)
            .first()
        )
        if survey is None:
            logger.warning("task_notify_survey_published: survey %s not found", survey_id)
            return 0

        count = notify_survey_published(survey)

        if should_email_survey_published(survey) and count > 0:
            _email_publish_recipients(survey)

        return count
    except Exception as exc:
        logger.exception("task_notify_survey_published failed for survey %s", survey_id)
        raise self.retry(exc=exc)


def _email_publish_recipients(survey) -> int:
    """Email users who just received an in-app publish notification for this survey."""
    from apps.notifications.email import email_survey_published
    from apps.notifications.models import Notification

    notes = (
        Notification.objects.filter(
            type=Notification.Type.SURVEY_PUBLISHED,
            payload__survey_id=survey.pk,
        )
        .select_related("user")
        .order_by("id")[:500]
    )
    company_name = ""
    try:
        company_name = survey.company.name
    except Exception:
        company_name = "Company"

    from apps.notifications.preferences import wants_email

    sent = 0
    for n in notes:
        user = n.user
        if not user or not user.email:
            continue
        if not wants_email(user, Notification.Type.SURVEY_PUBLISHED):
            continue
        ok = email_survey_published(
            user=user,
            survey_title=survey.title,
            company_name=company_name,
            body=n.body,
            link=n.link,
            points_reward=survey.points_reward or 0,
        )
        if ok:
            sent += 1
    return sent


@shared_task(name="notifications.send_daily_digests")
def task_send_daily_digests() -> int:
    """Celery beat entry: daily unread-notification digests."""
    from apps.notifications.digests import run_digests
    from apps.notifications.preferences import NotificationPreference

    return run_digests(frequency=NotificationPreference.DigestFrequency.DAILY)


@shared_task(name="notifications.send_weekly_digests")
def task_send_weekly_digests() -> int:
    """Celery beat entry: weekly unread-notification digests."""
    from apps.notifications.digests import run_digests
    from apps.notifications.preferences import NotificationPreference

    return run_digests(frequency=NotificationPreference.DigestFrequency.WEEKLY)


@shared_task(
    bind=True,
    name="notifications.send_team_invite_email",
    max_retries=3,
    default_retry_delay=20,
)
def task_send_team_invite_email(
    self,
    user_id: int,
    company_id: int,
    role_label: str,
    body: str,
    link: str,
    reactivated: bool = False,
) -> bool:
    try:
        from django.contrib.auth import get_user_model

        from apps.companies.models import Company

        from .email import email_team_invite

        User = get_user_model()
        user = User.objects.filter(pk=user_id, is_active=True).first()
        company = Company.objects.filter(pk=company_id).first()
        if not user or not company:
            return False
        return email_team_invite(
            user=user,
            company=company,
            role_label=role_label,
            body=body,
            link=link,
            reactivated=reactivated,
        )
    except Exception as exc:
        logger.exception("task_send_team_invite_email failed")
        raise self.retry(exc=exc)
