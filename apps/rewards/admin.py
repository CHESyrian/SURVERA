from django.contrib import admin

from .models import (
    Badge,
    PointsTransaction,
    TaskDefinition,
    TaskProgress,
    UserBadge,
    UserProgress,
    XPTransaction,
)


@admin.register(PointsTransaction)
class PointsTransactionAdmin(admin.ModelAdmin):
    list_display = ("user", "amount", "reason", "balance_after", "created_at")
    list_filter = ("reason",)
    raw_id_fields = ("user", "response")


@admin.register(XPTransaction)
class XPTransactionAdmin(admin.ModelAdmin):
    list_display = ("user", "amount", "reason", "total_after", "level_after", "created_at")
    list_filter = ("reason",)
    raw_id_fields = ("user", "response")


@admin.register(UserProgress)
class UserProgressAdmin(admin.ModelAdmin):
    list_display = ("user", "level", "xp_total", "surveys_completed")
    raw_id_fields = ("user",)


@admin.register(Badge)
class BadgeAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "xp_bonus")


@admin.register(UserBadge)
class UserBadgeAdmin(admin.ModelAdmin):
    list_display = ("user", "badge", "created_at")
    raw_id_fields = ("user", "badge")


@admin.register(TaskDefinition)
class TaskDefinitionAdmin(admin.ModelAdmin):
    list_display = ("code", "kind", "title", "target_count", "honor_reward", "xp_reward", "is_active")
    list_filter = ("kind", "is_active")


@admin.register(TaskProgress)
class TaskProgressAdmin(admin.ModelAdmin):
    list_display = ("user", "definition", "period_key", "current_count", "completed_at")
    list_filter = ("definition__kind",)
    raw_id_fields = ("user", "definition")
