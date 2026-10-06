"""Send a test email to EMAIL_FOR_TEST (notifications / invites / codes smoke check)."""
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.notifications.email import (
    email_survey_published,
    email_team_invite,
    send_plain_test_email,
)


class Command(BaseCommand):
    help = (
        "Send a test email to EMAIL_FOR_TEST. "
        "Kinds: plain (default), invite, survey, all."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--kind",
            choices=["plain", "invite", "survey", "all"],
            default="plain",
            help="Which template/style to send.",
        )
        parser.add_argument(
            "--to",
            default="",
            help="Override recipient (default: settings.EMAIL_FOR_TEST).",
        )

    def handle(self, *args, **options):
        inbox = (options.get("to") or getattr(settings, "EMAIL_FOR_TEST", "") or "").strip()
        if not inbox:
            raise CommandError(
                "EMAIL_FOR_TEST is not set. "
                "Add EMAIL_FOR_TEST=surveracorp.test@gmail.com to .env"
            )

        kind = options["kind"]
        # Force delivery to the chosen inbox for this command run
        settings.EMAIL_FOR_TEST = inbox
        settings.EMAIL_REDIRECT_TO_TEST = True

        class _User:
            email = inbox
            username = "test-user"

            def get_username(self):
                return self.username

        class _Company:
            name = "SURVERA Test Co"
            pk = 1

        user = _User()
        company = _Company()
        sent = 0

        if kind in ("plain", "all"):
            ok = send_plain_test_email(
                subject="SURVERA: plain test email",
                body=f"Plain test delivered to {inbox}.",
            )
            self.stdout.write(
                self.style.SUCCESS("plain: ok") if ok else self.style.ERROR("plain: failed")
            )
            sent += int(ok)

        if kind in ("invite", "all"):
            ok = email_team_invite(
                user=user,
                company=company,
                role_label="Moderator",
                body="You were invited to the test company.",
                link="/companies/",
                reactivated=False,
            )
            self.stdout.write(
                self.style.SUCCESS("invite: ok") if ok else self.style.ERROR("invite: failed")
            )
            sent += int(ok)

        if kind in ("survey", "all"):
            ok = email_survey_published(
                user=user,
                survey_title="Test Survey",
                company_name=company.name,
                body="A new survey is available.",
                link="/r/take/1/",
                points_reward=10,
            )
            self.stdout.write(
                self.style.SUCCESS("survey: ok") if ok else self.style.ERROR("survey: failed")
            )
            sent += int(ok)

        if sent == 0:
            raise CommandError("No emails were sent successfully.")
        self.stdout.write(self.style.SUCCESS(f"Sent {sent} message(s) toward {inbox}"))
