from django.urls import path

from . import views

app_name = "notifications"

urlpatterns = [
    path("", views.notification_list, name="list"),
    path("badge/", views.notification_badge, name="badge"),
    path("test/", views.notification_send_test, name="send_test"),
    path("<int:pk>/open/", views.notification_open, name="open"),
    path("<int:pk>/read/", views.notification_mark_read, name="mark_read"),
    path("read-all/", views.notification_mark_all_read, name="mark_all_read"),
]
