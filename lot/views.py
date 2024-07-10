from django.urls import reverse_lazy
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from django.views.generic.base import TemplateView
from django.views.generic.edit import (
    CreateView,
    DeleteView,
    UpdateView,
    FormView
)
from dashboard.mixins import DashboardView
from lot.models import Lot
from lot.forms import LotsForm


class NewLotView(DashboardView, CreateView):
    template_name = "new_lot.html"
    title = _("New lot")
    breadcrumb = "lot / New lot"
    success_url = reverse_lazy('dashboard:unassigned_devices')
    model = Lot
    fields = (
        "type",
        "name",
        "code",
        "description",
        "closed",
    )

    def form_valid(self, form):
        form.instance.owner = self.request.user
        response = super().form_valid(form)
        return response


class DeleteLotView(DashboardView, DeleteView):
    template_name = "delete_lot.html"
    title = _("Delete lot")
    breadcrumb = "lot / Delete lot"
    success_url = reverse_lazy('dashboard:unassigned_devices')
    model = Lot
    fields = (
        "type",
        "name",
        "code",
        "description",
        "closed",
    )

    def form_valid(self, form):
        response = super().form_valid(form)
        return response


class EditLotView(DashboardView, UpdateView):
    template_name = "new_lot.html"
    title = _("Edit lot")
    breadcrumb = "Lot / Edit lot"
    success_url = reverse_lazy('dashboard:unassigned_devices')
    model = Lot
    fields = (
        "type",
        "name",
        "code",
        "description",
        "closed",
    )

    def get_form_kwargs(self):
        pk = self.kwargs.get('pk')
        self.object = get_object_or_404(self.model, pk=pk)
        # self.success_url = reverse_lazy('dashbiard:lot', args=[pk])
        kwargs = super().get_form_kwargs()
        return kwargs


class AddToLotView(DashboardView, FormView):
    template_name = "list_lots.html"
    title = _("Add to lots")
    breadcrumb = "lot / add to lots"
    success_url = reverse_lazy('dashboard:unassigned_devices')
    form_class = LotsForm

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        lots = Lot.objects.filter(owner=self.request.user)
        lots_incoming = lots.filter(type=Lot.Types.INCOMING).exists()
        lots_outgoing = lots.filter(type=Lot.Types.OUTGOING).exists()
        lots_temporal = lots.filter(type=Lot.Types.TEMPORAL).exists()
        context.update({
            'lots': lots,
            'incoming': lots_incoming,
            'outgoing': lots_outgoing,
            'temporal': lots_temporal
        })
        return context

    def get_form(self):
        form = super().get_form()
        # import pdb; pdb.set_trace()
        form.fields["lots"].queryset = Lot.objects.filter(owner=self.request.user)
        return form

    def form_valid(self, form):
        form.devices = self.get_session_devices()
        form.save()
        response = super().form_valid(form)
        return response


class DelToLotView(AddToLotView):
    title = _("Remove from lots")
    breadcrumb = "lot / remove from lots"

    def form_valid(self, form):
        form.devices = self.get_session_devices()
        form.remove()
        response = super().form_valid(form)
        return response


class LotsTemporalView(DashboardView, TemplateView):
    template_name = "lots.html"
    title = _("Temporal lots")
    breadcrumb = "lot / temporal lots"
    success_url = reverse_lazy('dashboard:unassigned_devices')
    lot_type = Lot.Types.TEMPORAL

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        lots = Lot.objects.filter(owner=self.request.user)
        context.update({
            'lots': lots.filter(type=self.lot_type),
        })
        return context

class LotsOutgoingView(LotsTemporalView):
    title = _("Outgoing lots")
    breadcrumb = "lot / outging lots"
    lot_type = Lot.Types.OUTGOING


class LotsIncomingView(LotsTemporalView):
    title = _("Incoming lots")
    breadcrumb = "lot / Incoming lots"
    lot_type = Lot.Types.INCOMING
