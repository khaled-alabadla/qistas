"""
Contract list, detail, create/edit and the guarded status action
(spec §37, §21, §33, docs/adr/0031).

Every staff member may view contracts (``contracts.view``); create / edit /
status changes require ``contracts.manage`` (the client-handler set —
**paralegal is view-only**). Writes go through ``contracts.services`` so the
audit trail + case timeline stay consistent. A contract is never deleted
(docs/adr/0022) — "cancel" is a status transition.
"""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST
from django.views.generic import DetailView, FormView, ListView

from cases.models import Case
from clients.models import Client
from contracts import services
from contracts.forms import ContractFilterForm, ContractForm, ContractStatusForm
from contracts.models import Contract
from contracts.selectors import contract_list
from core.permissions.capabilities import Capability, can
from core.permissions.decorators import require_capability
from core.permissions.mixins import CapabilityRequiredMixin
from core.querysets import assert_scoped

PAGE_SIZE = 25


def _get_contract(user, pk) -> Contract:
    qs = Contract.objects.for_user(user).select_related(
        "client", "case", "created_by", "updated_by"
    )
    assert_scoped(qs)
    return get_object_or_404(qs, pk=pk)


def _page(request, object_list):
    paginator = Paginator(object_list, PAGE_SIZE)
    page = paginator.get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)
    qs = params.urlencode()
    return page, paginator.count, (f"{qs}&" if qs else "")


class ContractListView(CapabilityRequiredMixin, LoginRequiredMixin, ListView):
    required_capability = Capability.CONTRACTS_VIEW
    template_name = "contracts/contract_list.html"
    context_object_name = "contracts"

    def get_queryset(self):
        self.filter_form = ContractFilterForm(self.request.GET or None)
        self.filter_form.is_valid()
        data = self.filter_form.cleaned_data if self.filter_form.is_bound else {}
        qs = contract_list(
            user=self.request.user,
            query=data.get("q", ""),
            status=data.get("status", ""),
            contract_type=data.get("contract_type", ""),
            case_id=self.request.GET.get("case", ""),
            client_id=self.request.GET.get("client", ""),
            expiring_soon=bool(data.get("expiring")),
        )
        assert_scoped(qs)
        return qs

    def get_context_data(self, **kwargs):
        page, count, querystring = _page(self.request, self.object_list)
        return {
            **super().get_context_data(object_list=page.object_list, **kwargs),
            "filter_form": self.filter_form,
            "page_obj": page,
            "contracts": page.object_list,
            "total_count": count,
            "querystring": querystring,
            "can_manage": can(self.request.user, Capability.CONTRACTS_MANAGE),
        }


class ContractDetailView(CapabilityRequiredMixin, LoginRequiredMixin, DetailView):
    required_capability = Capability.CONTRACTS_VIEW
    template_name = "contracts/contract_detail.html"
    context_object_name = "contract"

    def get_object(self, queryset=None):
        return _get_contract(self.request.user, self.kwargs["pk"])

    def get_context_data(self, **kwargs):
        from documents.selectors import contract_documents

        contract = self.object
        can_docs = can(self.request.user, Capability.DOCUMENTS_VIEW)
        return {
            **super().get_context_data(**kwargs),
            "can_manage": can(self.request.user, Capability.CONTRACTS_MANAGE),
            "can_documents": can_docs,
            "can_documents_manage": can(self.request.user, Capability.DOCUMENTS_MANAGE),
            "documents": contract_documents(contract) if can_docs else [],
            "status_form": ContractStatusForm(initial={"status": contract.status}),
        }


class _ContractFormMixin(CapabilityRequiredMixin, LoginRequiredMixin, FormView):
    required_capability = Capability.CONTRACTS_MANAGE
    form_class = ContractForm
    template_name = "contracts/contract_form.html"

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), "user": self.request.user}

    def get_success_url(self):
        return reverse("contracts:detail", args=[self.object.pk])


class ContractCreateView(_ContractFormMixin):
    def get_initial(self):
        initial = {}
        user = self.request.user
        case_id = self.request.GET.get("case")
        client_id = self.request.GET.get("client")
        if str(case_id).isdigit() and Case.objects.for_user(user).filter(pk=case_id).exists():
            initial["case"] = case_id
        if str(client_id).isdigit() and Client.objects.for_user(user).filter(pk=client_id).exists():
            initial["client"] = client_id
        return initial

    def form_valid(self, form):
        self.object = services.create_contract(
            actor=self.request.user, data=form.cleaned_data, request=self.request
        )
        messages.success(self.request, _("تمت إضافة العقد."))
        return redirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        return {**super().get_context_data(**kwargs), "is_create": True}


class ContractUpdateView(_ContractFormMixin):
    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            self.contract_obj = _get_contract(request.user, kwargs["pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), "instance": self.contract_obj}

    def form_valid(self, form):
        self.object = services.update_contract(
            actor=self.request.user,
            contract=self.contract_obj,
            data=form.cleaned_data,
            request=self.request,
        )
        messages.success(self.request, _("تم حفظ التعديلات."))
        return redirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        return {
            **super().get_context_data(**kwargs),
            "is_create": False,
            "contract": self.contract_obj,
        }


@require_POST
@require_capability(Capability.CONTRACTS_MANAGE)
def contract_status(request, pk):
    contract = _get_contract(request.user, pk)
    form = ContractStatusForm(request.POST)
    if form.is_valid():  # ChoiceField already constrains to the 4 statuses
        try:
            services.change_contract_status(
                actor=request.user,
                contract=contract,
                new_status=form.cleaned_data["status"],
                request=request,
            )
            messages.success(request, _("تم تحديث حالة العقد."))
        except ValidationError as exc:
            messages.error(request, exc.messages[0] if exc.messages else _("انتقال غير مسموح."))
    else:
        messages.error(request, _("حالة غير صالحة."))
    return redirect("contracts:detail", pk=pk)
