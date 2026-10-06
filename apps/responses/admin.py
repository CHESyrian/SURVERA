"""Admin control panel for responses, quality, and report review / penalties."""
from django.contrib import admin, messages
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from .models import Answer, QualityAssessment, Report, Response
from .penalties import dismiss_report, resolve_with_penalty


class AnswerInline(admin.TabularInline):
    model = Answer
    extra = 0
    readonly_fields = ("question", "value", "created_at")
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Response)
class ResponseAdmin(admin.ModelAdmin):
    list_display = ("id", "survey", "participant", "status", "started_at", "completed_at")
    list_filter = ("status",)
    raw_id_fields = ("survey", "participant")
    inlines = [AnswerInline]


@admin.register(QualityAssessment)
class QualityAssessmentAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "response",
        "survey",
        "user",
        "score",
        "tier",
        "honor_granted",
        "created_at",
    )
    list_filter = ("tier",)
    search_fields = ("user__email",)
    raw_id_fields = ("response", "survey", "user")
    readonly_fields = ("created_at", "updated_at")


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    """
    Staff control panel for moderation reports.

    Set penalty kind + parameters, then use list actions to execute.
    """

    list_display = (
        "id",
        "type",
        "status",
        "penalty_kind",
        "warning_number",
        "survey",
        "reported_user",
        "reporter",
        "created_at",
        "resolved_at",
    )
    list_filter = ("status", "type", "penalty_kind")
    search_fields = (
        "note",
        "resolution_note",
        "reporter__email",
        "reported_user__email",
        "survey__title",
    )
    raw_id_fields = (
        "reporter",
        "company",
        "survey",
        "response",
        "reported_user",
        "resolved_by",
    )
    readonly_fields = (
        "created_at",
        "updated_at",
        "resolved_at",
        "resolved_by",
        "penalty_executed_at",
        "warning_number",
        "related_summary",
        "response_answers_preview",
        "penalty_catalog_help",
    )
    actions = ["action_mark_reviewing", "action_dismiss", "action_apply_penalty"]

    fieldsets = (
        (
            _("Report"),
            {
                "fields": (
                    "type",
                    "status",
                    "note",
                    "reporter",
                    "created_at",
                    "updated_at",
                )
            },
        ),
        (
            _("Related data"),
            {
                "fields": (
                    "company",
                    "survey",
                    "response",
                    "reported_user",
                    "related_summary",
                    "response_answers_preview",
                )
            },
        ),
        (
            _("Review decision"),
            {
                "description": _(
                    "Choose a penalty kind and parameters, save if needed, then use "
                    "the action “Apply penalty & notify” or “Dismiss report & notify”. "
                    "Saving the form alone does not execute the penalty."
                ),
                "fields": (
                    "penalty_catalog_help",
                    "resolution_note",
                    "penalty_kind",
                    "penalty_reputation",
                    "penalty_rank_levels",
                    "penalty_freeze_days",
                    "penalty_points",
                ),
            },
        ),
        (
            _("Execution log"),
            {
                "fields": (
                    "warning_number",
                    "resolved_by",
                    "resolved_at",
                    "penalty_executed_at",
                )
            },
        ),
    )

    @admin.display(description=_("Penalty catalog"))
    def penalty_catalog_help(self, obj):
        return format_html(
            "<ul style='margin:0;padding-left:1.2rem;'>"
            "<li><b>Warning</b> — progressive: 1st −100 honor, 2nd −200 honor, "
            "3rd freeze 7 days, 4th freeze 30 days, 5th+ permanent close</li>"
            "<li><b>Honor points deduction</b> — set amount in “honor points to deduct”</li>"
            "<li><b>Rank reduction</b> — set “rank levels to drop” (e.g. 1 → level 7→6)</li>"
            "<li><b>Account freeze</b> — set “freeze duration (days)”</li>"
            "<li><b>Permanent account closure</b> — closes the account</li>"
            "</ul>"
        )

    @admin.display(description=_("Related summary"))
    def related_summary(self, obj: Report) -> str:
        if not obj or not obj.pk:
            return "—"
        parts = []
        if obj.survey_id:
            parts.append(f"Survey: #{obj.survey_id} — {obj.survey.title}")
        if obj.company_id:
            parts.append(f"Company: {obj.company.name}")
        if obj.response_id:
            parts.append(
                f"Response: #{obj.response_id} ({obj.response.get_status_display()})"
            )
        if obj.reported_user_id:
            u = obj.reported_user
            parts.append(
                f"Subject: {u.email} · Honor {u.honor_points} · Rank L{u.trust_level} "
                f"· Warnings {u.warning_count}"
            )
            if u.closed_at:
                parts.append("Subject: PERMANENTLY CLOSED")
            elif u.frozen_until:
                parts.append(f"Subject frozen until: {u.frozen_until}")
        if obj.reporter_id:
            parts.append(f"Reporter: {obj.reporter.email}")
        return format_html("<br>".join(parts)) if parts else "—"

    @admin.display(description=_("Answers preview"))
    def response_answers_preview(self, obj: Report) -> str:
        if not obj or not obj.response_id:
            return "—"
        try:
            from .services import build_response_answer_rows

            rows = build_response_answer_rows(obj.response)
        except Exception:
            return "—"
        if not rows:
            return "—"
        lines = []
        for row in rows[:30]:
            q = row["question"]
            val = row["display_value"] or "—"
            lines.append(f"{q.order}. {q.text[:80]} → {val[:120]}")
        more = len(rows) - 30
        if more > 0:
            lines.append(f"… +{more} more")
        return format_html("<br>".join(lines))

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related(
                "survey",
                "company",
                "response",
                "reported_user",
                "reporter",
                "resolved_by",
            )
        )

    @admin.action(description=_("Mark selected as reviewing"))
    def action_mark_reviewing(self, request, queryset):
        updated = queryset.filter(
            status__in=[Report.Status.PENDING, Report.Status.REVIEWING]
        ).update(status=Report.Status.REVIEWING)
        self.message_user(request, _(f"{updated} report(s) marked reviewing."))

    @admin.action(description=_("Dismiss report & notify reporter"))
    def action_dismiss(self, request, queryset):
        ok = 0
        for report in queryset.select_related("reporter", "reported_user", "survey"):
            if not report.is_open:
                continue
            try:
                dismiss_report(
                    report=report,
                    admin_user=request.user,
                    resolution_note=report.resolution_note
                    or "Reviewed and dismissed by staff.",
                )
                ok += 1
            except Exception as e:
                self.message_user(
                    request, _(f"Report #{report.pk}: {e}"), level=messages.ERROR
                )
        self.message_user(
            request,
            _(f"Dismissed {ok} report(s). Reporter notified (in-app + email)."),
        )

    @admin.action(description=_("Apply penalty & notify both parties"))
    def action_apply_penalty(self, request, queryset):
        ok = 0
        for report in queryset.select_related(
            "reporter", "reported_user", "survey", "response"
        ):
            if not report.is_open:
                continue
            kind = report.penalty_kind or Report.PenaltyKind.WARNING
            if kind == Report.PenaltyKind.NONE:
                kind = Report.PenaltyKind.WARNING
            try:
                resolve_with_penalty(
                    report=report,
                    admin_user=request.user,
                    penalty_kind=kind,
                    penalty_reputation=report.penalty_reputation or 0,
                    penalty_points=report.penalty_points or 0,
                    penalty_rank_levels=report.penalty_rank_levels or 1,
                    penalty_freeze_days=report.penalty_freeze_days or 0,
                    resolution_note=report.resolution_note
                    or "Reviewed by staff; penalty applied.",
                )
                ok += 1
            except Exception as e:
                self.message_user(
                    request, _(f"Report #{report.pk}: {e}"), level=messages.ERROR
                )
        self.message_user(
            request,
            _(
                f"Resolved {ok} report(s) with penalty. "
                "Reporter and subject notified (in-app + email)."
            ),
        )
