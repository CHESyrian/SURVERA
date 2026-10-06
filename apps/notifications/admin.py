from django.contrib import admin

from .models import Notification
from .preferences import NotificationPreference


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "type", "title", "read_at", "created_at")
    list_filter = ("type", "read_at")
    search_fields = ("title", "body", "user__email", "user__username")
    raw_id_fields = ("user",)
    readonly_fields = ("created_at", "updated_at")


@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "inapp_survey_published",
        "email_survey_published",
        "inapp_team_invite",
        "email_team_invite",
        "updated_at",
    )
    raw_id_fields = ("user",)
    search_fields = ("user__email", "user__username")
