"""
Reports — thin views (docs/adr/0034).

* ``ReportsIndexView`` — the menu, showing only the reports whose gating
  capability the user holds.
* ``ReportView`` — renders one report as HTML (paginated) or, with
  ``?format=csv``, streams the CSV. **Authorization is checked before any data
  is fetched or any file is generated** (spec Phase 10 §6, §11); a CSV export is
  audited (spec Phase 10 §17).

There is no JSON / chart endpoint — every figure is server-rendered into the
page and inherits the page's authorization (spec Phase 10 §16).
"""

from __future__ import annotations

import datetime as dt

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.http import Http404, HttpResponseBadRequest
from django.utils.translation import gettext as _
from django.views.generic import TemplateView, View
from django.views.generic.base import ContextMixin

from audit.events import log_event
from audit.models import AuditAction
from core.permissions.capabilities import can
from reports import registry
from reports.framework import csv_response

PAGE_SIZE = 100


class ReportsIndexView(LoginRequiredMixin, TemplateView):
    template_name = "reports/index.html"

    def get_context_data(self, **kwargs):
        visible = registry.visible_reports(self.request.user)
        return {
            **super().get_context_data(**kwargs),
            "general_reports": [r for r in visible if r.group == "general"],
            "financial_reports": [r for r in visible if r.group == "financial"],
            "has_any": bool(visible),
        }


class ReportView(LoginRequiredMixin, ContextMixin, View):
    template_name = "reports/report.html"

    def get(self, request, slug):
        report = registry.get_report(slug)
        if report is None:
            raise Http404

        # ── authorization first — before any query or file generation ──
        if not can(request.user, report.capability):
            raise PermissionDenied(_("لا تملك صلاحية الوصول إلى هذا التقرير."))

        form = report.form_class(request.GET or None, user=request.user)
        wants_csv = request.GET.get("format") == "csv"

        filters = form.resolved_filters()  # None ⇒ bound form failed validation
        result = None if filters is None else report.builder(user=request.user, filters=filters)

        if wants_csv:
            if result is None:  # invalid filters
                return HttpResponseBadRequest(_("مرشّحات غير صالحة — تعذّر التصدير."))
            self._audit_export(request, report, filters, result)
            return csv_response(result, self._filename(report))

        from django.shortcuts import render

        context = self.get_context_data(
            report=report, form=form, result=result, **self._page(request, result)
        )
        return render(request, self.template_name, context)

    # ── helpers ──────────────────────────────────────────────────────────
    @staticmethod
    def _page(request, result):
        if result is None:
            return {"page_obj": None, "querystring": ""}
        paginator = Paginator(result.rows, PAGE_SIZE)
        page = paginator.get_page(request.GET.get("page"))
        params = request.GET.copy()
        params.pop("page", None)
        params.pop("format", None)
        qs = params.urlencode()
        return {
            "page_obj": page,
            "querystring": (f"{qs}&" if qs else ""),
            "paginator": paginator,
        }

    @staticmethod
    def _filename(report) -> str:
        # server-generated, no user input (spec Phase 10 §11/§12)
        return f"qistas-{report.slug}-{dt.date.today().isoformat()}.csv"

    @staticmethod
    def _audit_export(request, report, resolved_filters, result) -> None:
        if not report.audit_export:
            return
        # metadata only — scalar filter values, never free text or row content
        # (ADR-0009 / spec Phase 10 §17). `redact()` is applied by log_event.
        filters = {}
        for key, value in (resolved_filters or {}).items():
            if value in (None, "", False):
                continue
            filters[key] = getattr(value, "pk", None) or (
                value.isoformat() if isinstance(value, dt.date) else str(value)
            )
        log_event(
            request,
            AuditAction.REPORT_EXPORTED,
            entity_type="reports.report",
            entity_id=report.slug,
            object_repr=str(report.label),
            changes={
                "report": report.slug,
                "format": "csv",
                "rows": result.row_count,
                "truncated": result.truncated,
                "financial": report.is_financial,
                "filters": filters,
            },
        )
