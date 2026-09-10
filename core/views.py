"""Core views: authenticated landing page, dev styleguide, error handlers."""

from __future__ import annotations

from django.conf import settings
from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.views.decorators.csrf import requires_csrf_token
from django.views.generic import TemplateView

from core.permissions.mixins import CapabilityRequiredMixin


class LandingView(TemplateView):
    """The authenticated home page = the operational dashboard (spec §17–19,
    docs/adr/0033). All the aggregation lives in ``dashboard.selectors`` (a
    read/analytics layer); this view is a thin shell. The my-tasks / overdue /
    upcoming-deadline / expiring-contract / outstanding-invoice surfaces that
    Phases 5–8 seeded here are now folded into the dashboard's KPI row +
    Attention + Deadlines sections. Login is enforced by
    ``accounts.middleware.LoginRequiredMiddleware``; per-widget access
    (finance, confidential activity) is capability-filtered inside
    ``build_dashboard`` — the page itself is every authenticated user's home."""

    template_name = "dashboard/dashboard.html"

    def get_context_data(self, **kwargs):
        from dashboard.selectors import build_dashboard

        return {**super().get_context_data(**kwargs), **build_dashboard(self.request.user)}


class SettingsView(CapabilityRequiredMixin, TemplateView):
    """Settings hub — office-manager only. Real settings screens arrive with
    their features; Phase 1 links to the Django admin."""

    template_name = "core/settings.html"
    required_capability = "settings.view"


class StyleguideView(TemplateView):
    """Dev-only component gallery. 404 in production."""

    template_name = "core/styleguide.html"

    def dispatch(self, request, *args, **kwargs):
        if not settings.DEBUG:
            raise Http404
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["demo_headers"] = ["رقم القضية", "الموكل", "الحالة"]
        ctx["demo_rows"] = [
            ["C-2026-0087", "شركة الوفاق التجارية", "قيد المتابعة"],
            ["C-2026-0088", "محمود أحمد", "قيد المحاكمة"],
        ]
        ctx["empty_rows"] = []
        return ctx


def healthz(request) -> HttpResponse:
    return HttpResponse("ok", content_type="text/plain")


# ── Error handlers (themed, Arabic, RTL) ────────────────────
@requires_csrf_token
def handler400(request, exception=None, template_name="errors/400.html"):
    return render(request, template_name, status=400)


@requires_csrf_token
def handler403(request, exception=None, template_name="errors/403.html"):
    return render(request, template_name, status=403)


@requires_csrf_token
def handler404(request, exception=None, template_name="errors/404.html"):
    return render(request, template_name, status=404)


@requires_csrf_token
def handler500(request, template_name="errors/500.html"):
    # Render without the request context processors: if the 500 was caused by a
    # context processor, re-running them here would mask it with another 500.
    from django.template.loader import render_to_string

    html = render_to_string(template_name, {"APP_NAME": "قِسطاس"})
    return HttpResponse(html, status=500)
