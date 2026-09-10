"""
The notification inbox (spec §45, §99, docs/adr/0035).

Every path is **recipient-scoped** through ``Notification.objects.for_user`` —
a user only ever sees, opens, or marks their own rows, and a tampered id is a
**404** (strict per-user siloing). ``notifications.view`` is an all-staff nav
capability; the real boundary is the recipient scope.
"""

from __future__ import annotations

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from django.views.generic import ListView

from core.permissions.capabilities import Capability
from core.permissions.decorators import require_capability
from core.permissions.mixins import CapabilityRequiredMixin
from core.querysets import assert_scoped
from notifications import services
from notifications.models import Notification, NotificationCategory
from notifications.selectors import notification_list, unread_count

PAGE_SIZE = 20


def _safe_next(request, fallback: str) -> str:
    nxt = request.POST.get("next") or request.GET.get("next") or ""
    if nxt and url_has_allowed_host_and_scheme(
        nxt, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return nxt
    return fallback


class NotificationListView(CapabilityRequiredMixin, LoginRequiredMixin, ListView):
    required_capability = Capability.NOTIFICATIONS_VIEW
    template_name = "notifications/notification_list.html"
    context_object_name = "notifications"

    def get_queryset(self):
        self.unread_only = self.request.GET.get("filter") == "unread"
        self.category = self.request.GET.get("category", "")
        qs = notification_list(
            user=self.request.user,
            unread_only=self.unread_only,
            category=self.category,
        )
        assert_scoped(qs)
        return qs

    def get_context_data(self, **kwargs):
        paginator = Paginator(self.object_list, PAGE_SIZE)
        page = paginator.get_page(self.request.GET.get("page"))
        params = self.request.GET.copy()
        params.pop("page", None)
        qs = params.urlencode()
        return {
            **super().get_context_data(object_list=page.object_list, **kwargs),
            "notifications": page.object_list,
            "page_obj": page,
            "querystring": f"{qs}&" if qs else "",
            "total_count": paginator.count,
            "unread_count": unread_count(self.request.user),
            "unread_only": self.unread_only,
            "active_category": self.category,
            "categories": NotificationCategory.choices,
        }


@require_POST
@require_capability(Capability.NOTIFICATIONS_VIEW)
def notification_mark_read(request, pk):
    services.mark_read(user=request.user, notification_id=pk)
    return redirect(_safe_next(request, reverse("notifications:list")))


@require_POST
@require_capability(Capability.NOTIFICATIONS_VIEW)
def notification_mark_all_read(request):
    services.mark_all_read(user=request.user)
    return redirect(_safe_next(request, reverse("notifications:list")))


@require_capability(Capability.NOTIFICATIONS_VIEW)
def notification_open(request, pk):
    """Mark the notification read and forward to its target record. The target
    view enforces its own domain authorization — this is not a bypass."""
    qs = Notification.objects.for_user(request.user)
    assert_scoped(qs)
    obj = get_object_or_404(qs, pk=pk)
    obj.mark_read()
    if obj.url and url_has_allowed_host_and_scheme(
        obj.url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return redirect(obj.url)
    return redirect("notifications:list")
