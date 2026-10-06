"""
URL configuration for SURVERA project.
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from apps.common.views import home

urlpatterns = [
    path("admin/", admin.site.urls),
    path("i18n/", include("django.conf.urls.i18n")),
    path("accounts/", include("apps.accounts.urls")),
    path("surveys/", include("apps.surveys.urls")),
    path("companies/", include("apps.companies.urls")),
    path("r/", include("apps.responses.urls")),
    path("notifications/", include("apps.notifications.urls")),
    path("rewards/", include("apps.rewards.urls")),
    path("", home, name="home"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    try:
        import debug_toolbar

        urlpatterns = [
            path("__debug__/", include(debug_toolbar.urls)),
        ] + urlpatterns
    except ImportError:
        pass
