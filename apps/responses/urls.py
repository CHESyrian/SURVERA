from django.urls import path
from . import views

app_name = "responses"

urlpatterns = [
    path("take/<int:pk>/", views.take_survey, name="take"),
    path("thanks/<int:pk>/", views.thanks, name="thanks"),
    path("survey/<int:pk>/responses/", views.response_list, name="list"),
    path("survey/<int:pk>/export.csv", views.export_csv, name="export_csv"),
    path("detail/<int:pk>/", views.response_detail, name="detail"),
    path("report/<int:pk>/", views.report_response, name="report"),
]
