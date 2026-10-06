from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("register/", views.register, name="register"),
    path("login/", views.SurveraLoginView.as_view(), name="login"),
    path("logout/", views.SurveraLogoutView.as_view(), name="logout"),
    path("profile/", views.profile_view, name="profile"),
    path("password/change/", views.SurveraPasswordChangeView.as_view(), name="password_change"),
    path("verify-email/", views.verify_email, name="verify_email"),
    path("verify-email/resend/", views.resend_verification, name="resend_verification"),
]
