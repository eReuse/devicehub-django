from django.urls import reverse_lazy
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from django.views.generic.edit import (
    CreateView,
    UpdateView,
)
from dashboard.mixins import DashboardView, DetailsMixin
from device.models import Device, PhysicalProperties


class NewDeviceView(DashboardView, CreateView):
    template_name = "new_device.html"
    title = _("New Device")
    breadcrumb = "Device / New Device"
    success_url = reverse_lazy('dashboard:unassigned_devices')
    model = Device
    fields = (
        'type',
        "model",
        "manufacturer",
        "serial_number",
        "part_number",
        "brand",
        "generation",
        "version",
        "production_date",
        "variant",
        "family",
    )

    def form_valid(self, form):
        form.instance.owner = self.request.user
        response = super().form_valid(form)
        PhysicalProperties.objects.create(device=form.instance)
        return response
    

class EditDeviceView(DashboardView, UpdateView):
    template_name = "new_device.html"
    title = _("Update Device")
    breadcrumb = "Device / Update Device"
    success_url = reverse_lazy('dashboard:unassigned_devices')
    model = Device
    fields = (
        'type',
        "model",
        "manufacturer",
        "serial_number",
        "part_number",
        "brand",
        "generation",
        "version",
        "production_date",
        "variant",
        "family",
    )

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


class PhysicalView(DashboardView, UpdateView):
    template_name = "physical_properties.html"
    title = _("Physical Properties")
    breadcrumb = "Device / Physical properties"
    success_url = reverse_lazy('dashboard:unassigned_devices')
    model = PhysicalProperties
    fields = (
        "weight",
        "width",
        "height",
        "depth",
        "color",
        "image",
    )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'device': self.device,
        })
        return context

    def get_form_kwargs(self):
        pk = self.kwargs.get('pk')
        self.device = get_object_or_404(Device, pk=pk)
        try:
            self.object = self.device.physicalproperties
        except Exception:
            self.object = PhysicalProperties.objects.create(device=self.device)
        kwargs = super().get_form_kwargs()
        return kwargs
    
    def form_valid(self, form):
        self.success_url = reverse_lazy('device:details', args=[self.device.id])
        response = super().form_valid(form)
        return response
    

