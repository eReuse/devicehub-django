import json

from django.urls import reverse_lazy
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from django.views.generic.edit import (
    CreateView,
    UpdateView,
)
from django.views.generic.base import TemplateView
from dashboard.mixins import DashboardView, DetailsMixin
from snapshot.models import Annotation
from snapshot.xapian import search
from lot.models import LotTag
from device.models import Device


class NewDeviceView(DashboardView, CreateView):
    template_name = "new_device.html"
    title = _("New Device")
    breadcrumb = "Device / New Device"
    success_url = reverse_lazy('dashboard:unassigned_devices')
    model = Device

    def form_valid(self, form):
        form.instance.owner = self.request.user
        response = super().form_valid(form)
        return response


class EditDeviceView(DashboardView, UpdateView):
    template_name = "new_device.html"
    title = _("Update Device")
    breadcrumb = "Device / Update Device"
    success_url = reverse_lazy('dashboard:unassigned_devices')
    model = Device

    def get_form_kwargs(self):
        pk = self.kwargs.get('pk')
        self.object = get_object_or_404(self.model, pk=pk)
        self.success_url = reverse_lazy('device:details', args=[pk])
        kwargs = super().get_form_kwargs()
        return kwargs


class DetailsView(DetailsMixin):
    template_name = "details.html"
    title = _("Device")
    breadcrumb = "Device / Details"
    model = Device

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        self.object.initial()
        lot_tags = LotTag.objects.filter(owner=self.request.user)
        context.update({
            'snapshot': self.object.get_last_snapshot(),
            'lot_tags': lot_tags,
        })
        return context


class AddAnnotationView(DashboardView, CreateView):
    template_name = "new_device.html"
    title = _("New annotation")
    breadcrumb = "Device / New annotation"
    success_url = reverse_lazy('dashboard:unassigned_devices')
    model = Annotation
    fields = ("key", "value")

    def form_valid(self, form):
        self.device.get_annotations()
        self.device.get_uuids()
        form.instance.owner = self.request.user
        form.instance.device = self.device
        form.instance.uuid = self.device.uuids[0]
        form.instance.type = Annotation.Type.USER
        response = super().form_valid(form)
        return response

    def get_form_kwargs(self):
        pk = self.kwargs.get('pk')
        self.device = get_object_or_404(Device, pk=pk)
        self.success_url = reverse_lazy('device:details', args=[pk])
        kwargs = super().get_form_kwargs()
        return kwargs

    def get_success_url(self):
        url = super().get_success_url()
        import pdb; pdb.set_trace()
        return url


