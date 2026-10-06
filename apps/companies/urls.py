from django.urls import path

from . import views

app_name = "companies"

urlpatterns = [
    path("", views.company_list, name="list"),
    path("create/", views.company_create, name="create"),
    path("<int:pk>/team/", views.company_team, name="team"),
    path("<int:pk>/team/add/", views.company_member_add, name="member_add"),
    path(
        "<int:pk>/team/<int:membership_id>/role/",
        views.company_member_role,
        name="member_role",
    ),
    path(
        "<int:pk>/team/<int:membership_id>/remove/",
        views.company_member_remove,
        name="member_remove",
    ),
]
