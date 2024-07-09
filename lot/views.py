from django.urls import reverse_lazy
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from django.views.generic.edit import (
    CreateView,
    UpdateView,
)
from dashboard.mixins import DashboardView, DetailsMixin
from lot.models import Lot


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


class EditLotView(DashboardView, UpdateView):
    template_name = "new_lot.html"
    title = _("Update lot")
    breadcrumb = "Lot / Update lot"
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
