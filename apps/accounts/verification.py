"""Email verification by one-time code for SURVERA."""
from __future__ import annotations

import logging
import secrets
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.db import models, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.common.models import TimeStampedModel

logger = logging.getLogger(__name__)

CODE_LENGTH = 6
CODE_TTL_MINUTES = 15
MAX_ACTIVE_CODES_PER_USER = 3
# Minimum seconds between issued codes for the same user (self-serve resend).
RESEND_COOLDOWN_SECONDS = 60


class EmailVerificationCode(TimeStampedModel):
    """Short-lived numeric code sent to the user's email."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="email_verification_codes",
    )
    code = models.CharField(max_length=CODE_LENGTH, db_index=True)
    expires_at = models.DateTimeField(db_index=True)
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "code", "used_at"]),
        ]
        verbose_name = _("email verification code")
        verbose_name_plural = _("email verification codes")

    def __str__(self) -> str:
        return f"{self.user_id}:{self.code}"

    @property
    def is_valid(self) -> bool:
        if self.used_at is not None:
            return False
        return timezone.now() < self.expires_at


def _generate_code() -> str:
    # 6-digit numeric, zero-padded (000000–999999)
    return f"{secrets.randbelow(10**CODE_LENGTH):0{CODE_LENGTH}d}"


def seconds_until_resend_allowed(user) -> int:
    """
    Seconds remaining before the user may request another code.
    0 means resend is allowed now.
    """
    last = (
        EmailVerificationCode.objects.filter(user=user)
        .order_by("-created_at")
        .values_list("created_at", flat=True)
        .first()
    )
    if last is None:
        return 0
    elapsed = (timezone.now() - last).total_seconds()
    remaining = RESEND_COOLDOWN_SECONDS - elapsed
    return max(0, int(remaining))


def can_resend_code(user) -> tuple[bool, int]:
    """Return (allowed, seconds_remaining)."""
    wait = seconds_until_resend_allowed(user)
    return wait == 0, wait


@transaction.atomic
def create_verification_code(user) -> EmailVerificationCode:
    """Invalidate excess active codes and issue a fresh one."""
    now = timezone.now()
    # Expire old unused codes beyond the keep window
    EmailVerificationCode.objects.filter(
        user=user,
        used_at__isnull=True,
        expires_at__lt=now,
    ).delete()

    active = EmailVerificationCode.objects.filter(
        user=user,
        used_at__isnull=True,
        expires_at__gte=now,
    ).order_by("-created_at")
    # Keep at most MAX_ACTIVE - 1 so the new one fits
    for old in active[MAX_ACTIVE_CODES_PER_USER - 1 :]:
        old.used_at = now
        old.save(update_fields=["used_at", "updated_at"])

    return EmailVerificationCode.objects.create(
        user=user,
        code=_generate_code(),
        expires_at=now + timedelta(minutes=CODE_TTL_MINUTES),
    )


def send_verification_email(user, code: EmailVerificationCode) -> bool:
    """Send the verification code email. Returns True on success."""
    from apps.notifications.email import resolve_recipient_email

    subject = _("SURVERA – Your verification code")
    body = _(
        "Hi %(name)s,\n\n"
        "Your SURVERA email verification code is:\n\n"
        "    %(code)s\n\n"
        "This code expires in %(minutes)s minutes.\n"
        "If you did not request this, you can ignore this email.\n\n"
        "— SURVERA"
    ) % {
        "name": user.get_username() or user.email,
        "code": code.code,
        "minutes": CODE_TTL_MINUTES,
    }
    recipient = resolve_recipient_email(getattr(user, "email", "") or "")
    if not recipient:
        return False
    try:
        send_mail(
            subject=str(subject),
            message=str(body),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient],
            fail_silently=False,
        )
        return True
    except Exception:
        logger.exception("Failed to send verification email to %s", recipient)
        return False


def issue_and_send_code(
    user,
    *,
    bypass_rate_limit: bool = False,
) -> tuple[EmailVerificationCode | None, str]:
    """
    Create a code and email it.

    Returns (code_or_None, message).
    When rate-limited, code is None and message explains the wait.
    """
    if not bypass_rate_limit:
        allowed, wait = can_resend_code(user)
        if not allowed:
            return None, str(
                _("Please wait %(seconds)s seconds before requesting a new code.")
                % {"seconds": wait}
            )

    code = create_verification_code(user)
    ok = send_verification_email(user, code)
    if not ok:
        return None, str(_("Could not send the email. Please try again in a moment."))
    return code, str(_("A new verification code was sent to your email."))


@transaction.atomic
def verify_code(user, raw_code: str) -> tuple[bool, str]:
    """
    Attempt to verify ``raw_code`` for ``user``.

    Returns (success, message).
    """
    code_str = (raw_code or "").strip()
    if not code_str or len(code_str) != CODE_LENGTH or not code_str.isdigit():
        return False, str(_("Enter the 6-digit code from your email."))

    now = timezone.now()
    entry = (
        EmailVerificationCode.objects.select_for_update()
        .filter(
            user=user,
            code=code_str,
            used_at__isnull=True,
            expires_at__gte=now,
        )
        .order_by("-created_at")
        .first()
    )
    if not entry:
        return False, str(_("Invalid or expired code. Request a new one."))

    entry.used_at = now
    entry.save(update_fields=["used_at", "updated_at"])

    if not user.is_email_verified:
        user.is_email_verified = True
        user.save(update_fields=["is_email_verified"])

    # Invalidate remaining unused codes
    EmailVerificationCode.objects.filter(user=user, used_at__isnull=True).update(
        used_at=now
    )

    try:
        from apps.accounts.honor import grant_email_verified_honor

        grant_email_verified_honor(user)
    except Exception:
        logger.exception(
            "Failed to grant email-verified honor user_id=%s", getattr(user, "pk", None)
        )

    return True, str(_("Email verified successfully."))


def mark_email_verified(user) -> None:
    """Admin/helper: mark user verified and invalidate outstanding codes."""
    now = timezone.now()
    if not user.is_email_verified:
        user.is_email_verified = True
        user.save(update_fields=["is_email_verified"])
    EmailVerificationCode.objects.filter(user=user, used_at__isnull=True).update(
        used_at=now
    )
    try:
        from apps.accounts.honor import grant_email_verified_honor

        grant_email_verified_honor(user)
    except Exception:
        logger.exception(
            "Failed to grant email-verified honor user_id=%s", getattr(user, "pk", None)
        )
