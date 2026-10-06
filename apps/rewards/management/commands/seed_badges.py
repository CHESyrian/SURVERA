"""Seed default SURVERA badges."""
from django.core.management.base import BaseCommand

from apps.rewards.models import Badge

DEFAULT_BADGES = [
    {
        "code": "first-steps",
        "name": "First Steps",
        "description": "Reach level 2.",
        "icon": "🌱",
        "xp_bonus": 10,
        "criteria": {"min_level": 2},
    },
    {
        "code": "rising-star",
        "name": "Rising Star",
        "description": "Reach level 5.",
        "icon": "⭐",
        "xp_bonus": 50,
        "criteria": {"min_level": 5},
    },
    {
        "code": "veteran",
        "name": "Veteran",
        "description": "Reach level 10.",
        "icon": "🏆",
        "xp_bonus": 100,
        "criteria": {"min_level": 10},
    },
    {
        "code": "first-response",
        "name": "First Response",
        "description": "Complete your first survey.",
        "icon": "✍️",
        "xp_bonus": 15,
        "criteria": {"min_surveys_completed": 1},
    },
    {
        "code": "survey-regular",
        "name": "Survey Regular",
        "description": "Complete 10 surveys.",
        "icon": "📋",
        "xp_bonus": 40,
        "criteria": {"min_surveys_completed": 10},
    },
    {
        "code": "survey-champion",
        "name": "Survey Champion",
        "description": "Complete 50 surveys.",
        "icon": "🏅",
        "xp_bonus": 150,
        "criteria": {"min_surveys_completed": 50},
    },
    {
        "code": "trusted-voice",
        "name": "Trusted Voice",
        "description": "Reach 100 Reputation.",
        "icon": "🛡️",
        "xp_bonus": 25,
        "criteria": {"min_honor": 100},
    },
    {
        "code": "distinguished",
        "name": "Distinguished",
        "description": "Reach 500 Reputation.",
        "icon": "💎",
        "xp_bonus": 75,
        "criteria": {"min_honor": 500},
    },
    {
        "code": "survey-builder",
        "name": "Survey Builder",
        "description": "Create your first survey.",
        "icon": "🛠️",
        "xp_bonus": 20,
        "criteria": {"min_surveys_created": 1},
    },
]


class Command(BaseCommand):
    help = "Seed default badges (idempotent upsert by code)."

    def handle(self, *args, **options):
        created = 0
        updated = 0
        for data in DEFAULT_BADGES:
            obj, was_created = Badge.objects.update_or_create(
                code=data["code"],
                defaults={
                    "name": data["name"],
                    "description": data["description"],
                    "icon": data.get("icon", ""),
                    "xp_bonus": data.get("xp_bonus", 0),
                    "criteria": data.get("criteria") or {},
                },
            )
            if was_created:
                created += 1
            else:
                updated += 1
        self.stdout.write(
            self.style.SUCCESS(f"Badges seeded: {created} created, {updated} updated.")
        )
