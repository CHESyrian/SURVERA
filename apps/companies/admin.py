from django.contrib import admin

from .models import Company, CompanyMembership


class MembershipInline(admin.TabularInline):
    model = CompanyMembership
    extra = 0
    raw_id_fields = ("user",)


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "status", "created_at")
    list_filter = ("status",)
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [MembershipInline]


@admin.register(CompanyMembership)
class CompanyMembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "company", "role", "is_active", "created_at")
    list_filter = ("role", "is_active")
    search_fields = ("user__email", "company__name")
    raw_id_fields = ("user", "company")
