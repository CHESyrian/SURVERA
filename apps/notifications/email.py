"""Email delivery channel for notifications."""
from __future__ import annotations

import logging

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags

logger = logging.getLogger(__name__)


def absolute_url(path: str) -> str:
    """Build absolute URL from a relative path using SITE_URL."""
    base = (getattr(settings, "SITE_URL", None) or "http://localhost:8000").rstrip("/")
    if not path:
        return base
    if path.startswith("http://") or path.startswith("https://"):
        return path
    if not path.startswith("/"):
        path = "/" + path
    return f"{base}{path}"


def resolve_recipient_email(to_email: str) -> str:
    """
    Return the actual delivery address.

    When EMAIL_REDIRECT_TO_TEST is enabled and EMAIL_FOR_TEST is set,
    every message is delivered to EMAIL_FOR_TEST (local/manual testing).
    """
    test_inbox = (getattr(settings, "EMAIL_FOR_TEST", "") or "").strip()
    if test_inbox and getattr(settings, "EMAIL_REDIRECT_TO_TEST", False):
        return test_inbox
    return (to_email or "").strip()


def send_notification_email(
    *,
    to_email: str,
    subject: str,
    template_name: str,
    context: dict,
) -> bool:
    """
    Send a single notification email.

    Returns True on success, False on failure (never raises to callers).
    """
    recipient = resolve_recipient_email(to_email)
    if not recipient:
        return False
    try:
        ctx = {
            **context,
            "site_url": absolute_url(""),
            "site_name": "SURVERA",
        }
        html = render_to_string(template_name, ctx)
        text = strip_tags(html)
        send_mail(
            subject=subject[:200],
            message=text,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient],
            html_message=html,
            fail_silently=False,
        )
        if recipient != (to_email or "").strip():
            logger.info(
                "Email redirected: intended=%s delivered=%s subject=%s",
                to_email,
                recipient,
                subject[:80],
            )
        return True
    except Exception:
        logger.exception("Failed to send notification email to %s", recipient)
        return False


def email_team_invite(*, user, company, role_label: str, body: str, link: str, reactivated: bool) -> bool:
    subject = (
        f"SURVERA: Welcome back to {company.name}"
        if reactivated
        else f"SURVERA: You've been added to {company.name}"
    )
    return send_notification_email(
        to_email=getattr(user, "email", "") or "",
        subject=subject,
        template_name="notifications/email/team_invite.html",
        context={
            "user": user,
            "company": company,
            "role_label": role_label,
            "body": body,
            "action_url": absolute_url(link),
            "reactivated": reactivated,
        },
    )


def email_survey_published(
    *,
    user,
    survey_title: str,
    company_name: str,
    body: str,
    link: str,
    points_reward: int = 0,
) -> bool:
    subject = f"SURVERA: New survey — {survey_title[:80]}"
    return send_notification_email(
        to_email=getattr(user, "email", "") or "",
        subject=subject,
        template_name="notifications/email/survey_published.html",
        context={
            "user": user,
            "survey_title": survey_title,
            "company_name": company_name,
            "body": body,
            "action_url": absolute_url(link),
            "points_reward": points_reward,
        },
    )


def send_plain_test_email(*, subject: str = "SURVERA test email", body: str = "") -> bool:
    """Send a simple message to EMAIL_FOR_TEST. Used by management command / smoke tests."""
    recipient = (getattr(settings, "EMAIL_FOR_TEST", "") or "").strip()
    if not recipient:
        logger.error("EMAIL_FOR_TEST is not configured")
        return False
    text = body or (
        "This is a test message from SURVERA.\n"
        f"If you received this at {recipient}, email delivery is working.\n"
    )
    try:
        send_mail(
            subject=subject[:200],
            message=text,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient],
            fail_silently=False,
        )
        return True
    except Exception:
        logger.exception("Failed to send test email to %s", recipient)
        return False
