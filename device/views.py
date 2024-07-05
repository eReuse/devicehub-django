from django.urls import reverse_lazy
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from django.views.generic.edit import (
    CreateView,
    UpdateView,
)
from dashboard.mixins import DashboardView, DetailsMixin
from device.forms import DeviceForm, PhysicalPropsForm
from device.models import Device, PhysicalProperties


class NewDeviceView(DashboardView, CreateView):
    template_name = "new_device.html"
    title = _("New Device")
    breadcrumb = "Device / New Device"
    form_class = DeviceForm
    success_url = reverse_lazy('dashboard:unassigned_devices')

    def form_valid(self, form):
        form.instance.owner = self.request.user
        response = super().form_valid(form)
        PhysicalProperties.objects.create(device=form.instance)
        return response
    

class DetailsView(DetailsMixin):
    template_name = "details.html"
    title = _("Device")
    breadcrumb = "Device / Details"
    model = Device


class PhysicalView(DashboardView, UpdateView):
    template_name = "physical_properties.html"
    title = _("Physical Properties")
    breadcrumb = "Device / Physical properties"
    form_class = PhysicalPropsForm
    success_url = reverse_lazy('dashboard:unassigned_devices')
    model = PhysicalProperties

    def get(self, request, *args, **kwargs):
        pk = kwargs['pk']
        self.device = get_object_or_404(Device, pk=pk)
        try:
            self.object = self.device.physicalproperties
        except Exception:
            self.object = PhysicalProperties.objects.create(device=self.device)
        self.initial.update({'instance': self.object})
        return super().get(request, *args, **kwargs)

    def get_form(self, form_class=None):
        """Return an instance of the form to be used in this view."""
        if form_class is None:
            form_class = self.get_form_class()
        # import pdb; pdb.set_trace()
        return form_class(**self.get_form_kwargs())

    def get_form_kwargs(self):
        """Return the keyword arguments for instantiating the form."""
        kwargs = {
            "initial": self.get_initial(),
            "prefix": self.get_prefix(),
        }

        if self.request.method in ("POST", "PUT"):
            kwargs.update(
                {
                    "data": self.request.POST,
                    "files": self.request.FILES,
                }
            )
        return kwargs

    def form_valid(self, form):
        self.success_url = reverse_lazy('device:details', self.device.id)
        form.instance.owner = self.request.user
        response = super().form_valid(form)
        return response
    

