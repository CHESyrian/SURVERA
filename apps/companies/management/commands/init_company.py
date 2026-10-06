"""Create the SURVERA platform company and attach superusers as admins."""
from django.core.management.base import BaseCommand

from apps.companies.services import (
    PLATFORM_COMPANY_NAME,
    PLATFORM_COMPANY_SLUG,
    ensure_all_superusers_on_platform,
    get_or_create_platform_company,
)


class Command(BaseCommand):
    help = (
        "Create the platform company 'SURVERA' (slug=survera) if missing, "
        "and add all superusers as company admins."
    )

    def handle(self, *args, **options):
        company = get_or_create_platform_company()
        self.stdout.write(
            self.style.SUCCESS(
                f"Platform company ready: {company.name} (slug={company.slug}, id={company.pk})"
            )
        )
        n = ensure_all_superusers_on_platform()
        self.stdout.write(
            self.style.SUCCESS(
                f"Superuser memberships ensured on {PLATFORM_COMPANY_NAME} "
                f"({n} created/updated)."
            )
        )
        self.stdout.write(
            f"Hint: run after migrate — python manage.py init_company"
        )
