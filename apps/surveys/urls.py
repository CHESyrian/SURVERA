from django.urls import path
from . import views

app_name = "surveys"

urlpatterns = [
    path("discover/", views.survey_discover, name="discover"),
    path("", views.survey_list, name="list"),
    path("create/", views.survey_create, name="create"),
    path("<int:pk>/", views.survey_detail, name="detail"),
    path("<int:pk>/edit/", views.survey_edit, name="edit"),
    path("<int:pk>/publish/", views.survey_publish, name="publish"),
    path("<int:pk>/analytics/", views.survey_analytics, name="analytics"),
    path("<int:survey_pk>/questions/add/", views.question_create, name="question_create"),
    path("<int:survey_pk>/questions/<int:pk>/edit/", views.question_edit, name="question_edit"),
    path("<int:survey_pk>/questions/<int:pk>/delete/", views.question_delete, name="question_delete"),
]
