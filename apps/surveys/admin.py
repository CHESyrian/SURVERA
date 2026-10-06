from django.contrib import admin
from .models import Question, Survey

class QuestionInline(admin.TabularInline):
    model = Question
    extra = 0

@admin.register(Survey)
class SurveyAdmin(admin.ModelAdmin):
    list_display = ("title", "status", "visibility", "is_paid", "is_frozen", "company", "created_at")
    list_filter = ("status", "is_frozen", "allow_anonymous", "visibility", "is_paid")
    search_fields = ("title",)
    inlines = [QuestionInline]

@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("text", "type", "survey", "order", "is_required")
    list_filter = ("type",)
