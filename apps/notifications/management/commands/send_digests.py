from django.core.management.base import BaseCommand

from apps.notifications.digests import run_digests
from apps.notifications.preferences import NotificationPreference


class Command(BaseCommand):
    help = "Send email digests (daily or weekly) for due users."

    def add_arguments(self, parser):
        parser.add_argument(
            "--frequency",
            choices=["daily", "weekly"],
            default="daily",
            help="Digest frequency to process",
        )

    def handle(self, *args, **options):
        freq = options["frequency"]
        if freq == "weekly":
            key = NotificationPreference.DigestFrequency.WEEKLY
        else:
            key = NotificationPreference.DigestFrequency.DAILY
        sent = run_digests(frequency=key)
        self.stdout.write(self.style.SUCCESS(f"Digests sent: {sent} ({freq})"))
