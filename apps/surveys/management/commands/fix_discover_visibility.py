"""Make active free surveys public so they appear on Discover."""
from django.core.management.base import BaseCommand

from apps.surveys.models import Survey


class Command(BaseCommand):
    help = "Set visibility=public on active free surveys (and clear members-only when free)."

    def handle(self, *args, **options):
        qs = Survey.objects.filter(status=Survey.Status.ACTIVE, is_paid=False).exclude(
            visibility=Survey.Visibility.PUBLIC
        )
        n = 0
        for s in qs:
            s.visibility = Survey.Visibility.PUBLIC
            s.targeting = {}
            s.points_reward = 0
            s.response_target = None
            s.save(
                update_fields=[
                    "visibility",
                    "targeting",
                    "points_reward",
                    "response_target",
                    "updated_at",
                ]
            )
            n += 1
        self.stdout.write(self.style.SUCCESS(f"Updated {n} active free survey(s) to public."))
