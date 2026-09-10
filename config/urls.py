"""Root URL configuration."""

from __future__ import annotations

from django.conf import settings
from django.contrib import admin
from django.urls import include, path

handler400 = "core.views.handler400"
handler403 = "core.views.handler403"
handler404 = "core.views.handler404"
handler500 = "core.views.handler500"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("accounts.urls")),
    path("clients/", include("clients.urls")),
    path("cases/", include("cases.urls")),
    path("courts/", include("courts.urls")),
    path("hearings/", include("hearings.urls")),
    path("agenda/", include("agenda.urls")),
    path("tasks/", include("tasks.urls")),
    path("documents/", include("documents.urls")),
    path("contracts/", include("contracts.urls")),
    path("finance/", include("finance.urls")),
    path("reports/", include("reports.urls")),
    path("notifications/", include("notifications.urls")),
    path("", include("core.urls")),
]

if settings.DEBUG and "debug_toolbar" in settings.INSTALLED_APPS:
    urlpatterns += [path("__debug__/", include("debug_toolbar.urls"))]
