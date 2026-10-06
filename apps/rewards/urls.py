from django.urls import path

from . import views

app_name = "rewards"

urlpatterns = [
    path("tasks/", views.tasks_page, name="tasks"),
    path("leaderboard/", views.leaderboard_page, name="leaderboard"),
    path("leaderboard/rows/", views.leaderboard_rows, name="leaderboard_rows"),
]
