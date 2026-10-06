from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _
from django.utils.translation import ngettext

from .models import HonorEvent, TrustEvent, User
from .verification import (
    EmailVerificationCode,
    issue_and_send_code,
    mark_email_verified,
)


@admin.register(EmailVerificationCode)
class EmailVerificationCodeAdmin(admin.ModelAdmin):
    list_display = ["user", "code", "expires_at", "used_at", "created_at"]
    list_filter = ["used_at"]
    search_fields = ["user__email", "code"]
    readonly_fields = ["created_at", "updated_at"]
    raw_id_fields = ["user"]


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    ordering = ["-date_joined"]
    list_display = [
        "email",
        "username",
        "user_type",
        "language",
        "is_email_verified",
        "is_staff",
        "is_active",
        "date_joined",
    ]
    list_filter = ["user_type", "language", "is_email_verified", "is_staff", "is_active"]
    search_fields = ["email", "username", "first_name", "last_name"]
    actions = [
        "action_mark_email_verified",
        "action_mark_email_unverified",
        "action_resend_verification_code",
    ]

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (
            _("Personal info"),
            {
                "fields": (
                    "username",
                    "first_name",
                    "last_name",
                    "language",
                    "date_of_birth",
                    "gender",
                )
            },
        ),
        (
            _("Type & verification"),
            {"fields": ("user_type", "is_email_verified", "honor_points", "trust_level", "trust_score", "warning_count", "frozen_until", "closed_at")},
        ),
        (
            _("Permissions"),
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                ),
            },
        ),
        (_("Important dates"), {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "email",
                    "username",
                    "password1",
                    "password2",
                    "user_type",
                    "is_email_verified",
                ),
            },
        ),
    )

    @admin.action(description=_("Mark selected users as email verified"))
    def action_mark_email_verified(self, request, queryset):
        count = 0
        for user in queryset:
            if not user.is_email_verified:
                mark_email_verified(user)
                count += 1
            else:
                mark_email_verified(user)  # still clear outstanding codes
        self.message_user(
            request,
            ngettext(
                "%d user marked as email verified.",
                "%d users marked as email verified.",
                count,
            )
            % count,
            messages.SUCCESS,
        )

    @admin.action(description=_("Mark selected users as email NOT verified"))
    def action_mark_email_unverified(self, request, queryset):
        updated = queryset.filter(is_email_verified=True).update(is_email_verified=False)
        self.message_user(
            request,
            ngettext(
                "%d user marked as not verified.",
                "%d users marked as not verified.",
                updated,
            )
            % updated,
            messages.WARNING if updated else messages.INFO,
        )

    @admin.action(description=_("Resend verification code (bypass rate limit)"))
    def action_resend_verification_code(self, request, queryset):
        sent = 0
        skipped = 0
        failed = 0
        for user in queryset:
            if user.is_email_verified:
                skipped += 1
                continue
            code, _msg = issue_and_send_code(user, bypass_rate_limit=True)
            if code:
                sent += 1
            else:
                failed += 1
        if sent:
            self.message_user(
                request,
                ngettext(
                    "Verification code sent to %d user.",
                    "Verification codes sent to %d users.",
                    sent,
                )
                % sent,
                messages.SUCCESS,
            )
        if skipped:
            self.message_user(
                request,
                ngettext(
                    "Skipped %d already-verified user.",
                    "Skipped %d already-verified users.",
                    skipped,
                )
                % skipped,
                messages.INFO,
            )
        if failed:
            self.message_user(
                request,
                ngettext(
                    "Failed to send code to %d user.",
                    "Failed to send codes to %d users.",
                    failed,
                )
                % failed,
                messages.ERROR,
            )



@admin.register(TrustEvent)
class TrustEventAdmin(admin.ModelAdmin):
    list_display = ["user", "old_score", "new_score", "delta", "reason", "created_by", "created_at"]
    list_filter = ["reason"]
    search_fields = ["user__email", "note"]
    raw_id_fields = ["user", "created_by"]
    readonly_fields = ["created_at"]



@admin.register(HonorEvent)
class HonorEventAdmin(admin.ModelAdmin):
    list_display = ["user", "amount", "balance_after", "reason", "level_after", "created_at"]
    list_filter = ["reason"]
    search_fields = ["user__email", "note"]
    raw_id_fields = ["user", "created_by"]
    readonly_fields = ["created_at"]
