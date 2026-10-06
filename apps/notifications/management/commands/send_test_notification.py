"""Send a test in-app notification to a user (or the first superuser)."""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.urls import reverse

from apps.notifications.models import Notification
from apps.notifications.services import notify_user

User = get_user_model()


class Command(BaseCommand):
    help = "Create a test in-app notification for a user."

    def add_arguments(self, parser):
        parser.add_argument(
            "--email",
            type=str,
            default="",
            help="Recipient email (default: first superuser or staff).",
        )
        parser.add_argument(
            "--title",
            type=str,
            default="Test notification",
            help="Notification title.",
        )
        parser.add_argument(
            "--body",
            type=str,
            default="This is a test in-app notification from SURVERA.",
            help="Notification body.",
        )
        parser.add_argument(
            "--count",
            type=int,
            default=1,
            help="How many test notifications to create (default 1).",
        )

    def handle(self, *args, **options):
        email = (options.get("email") or "").strip()
        if email:
            user = User.objects.filter(email__iexact=email).first()
            if not user:
                raise CommandError(f"No user with email {email!r}")
        else:
            user = (
                User.objects.filter(is_superuser=True, is_active=True).first()
                or User.objects.filter(is_staff=True, is_active=True).first()
                or User.objects.filter(is_active=True).first()
            )
            if not user:
                raise CommandError("No users in the database.")

        title = options["title"]
        body = options["body"]
        count = max(1, min(int(options["count"]), 20))
        link = reverse("notifications:list")

        created = 0
        for i in range(count):
            t = title if count == 1 else f"{title} ({i + 1}/{count})"
            note = notify_user(
                user=user,
                type=Notification.Type.SYSTEM,
                title=t,
                body=body,
                link=link,
                payload={"test": True, "index": i + 1},
            )
            if note:
                created += 1
            else:
                # Preferences may block system in-app; force-create for testing.
                Notification.objects.create(
                    user=user,
                    type=Notification.Type.SYSTEM,
                    title=t[:200],
                    body=body or "",
                    link=link,
                    payload={"test": True, "index": i + 1, "forced": True},
                )
                created += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Created {created} test notification(s) for {user.email}"
            )
        )
