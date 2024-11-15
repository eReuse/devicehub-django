from django.http import JsonResponse
from django.conf import settings
from django.urls import reverse_lazy
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, Http404
from django.utils.translation import gettext_lazy as _
from django.views.generic.edit import (
    CreateView,
    UpdateView,
    FormView,
    DeleteView,
)
from django.views.generic.base import TemplateView
from dashboard.mixins import DashboardView, Http403
from evidence.models import UserProperty, SystemProperty, Property
from lot.models import LotTag
from device.models import Device
from device.forms import DeviceFormSet
if settings.DPP:
    from dpp.models import Proof
    from dpp.api_dlt import PROOF_TYPE


class NewDeviceView(DashboardView, FormView):
    template_name = "new_device.html"
    title = _("New Device")
    breadcrumb = "Device / New Device"
    success_url = reverse_lazy('dashboard:unassigned_devices')
    form_class = DeviceFormSet

    def form_valid(self, form):
        form.save(self.request.user)
        response = super().form_valid(form)
        return response

    def form_invalid(self, form):
        response = super().form_invalid(form)
        return response


# class AddToLotView(DashboardView, FormView):
#     template_name = "list_lots.html"
#     title = _("Add to lots")
#     breadcrumb = "lot / add to lots"
#     success_url = reverse_lazy('dashboard:unassigned_devices')
#     form_class = LotsForm

#     def get_context_data(self, **kwargs):
#         context = super().get_context_data(**kwargs)
#         lots = Lot.objects.filter(owner=self.request.user)
#         lot_tags = LotTag.objects.filter(owner=self.request.user)
#         context.update({
#             'lots': lots,
#             'lot_tags':lot_tags,
#         })
#         return context

#     def get_form(self):
#         form = super().get_form()
#         form.fields["lots"].queryset = Lot.objects.filter(owner=self.request.user)
#         return form

#     def form_valid(self, form):
#         form.devices = self.get_session_devices()
#         form.save()
#         response = super().form_valid(form)
#         return response


class EditDeviceView(DashboardView, UpdateView):
    template_name = "new_device.html"
    title = _("Update Device")
    breadcrumb = "Device / Update Device"
    success_url = reverse_lazy('dashboard:unassigned_devices')
    model = SystemProperty

    def get_form_kwargs(self):
        pk = self.kwargs.get('pk')
        self.object = get_object_or_404(
            self.model,
            pk=pk,
            owner=self.request.user.institution
        )
        self.success_url = reverse_lazy('device:details', args=[pk])
        kwargs = super().get_form_kwargs()
        return kwargs


class DetailsView(DashboardView, TemplateView):
    template_name = "details.html"
    title = _("Device")
    breadcrumb = "Device / Details"
    model = SystemProperty

    def get(self, request, *args, **kwargs):
        self.pk = kwargs['pk']
        self.object = Device(id=self.pk)
        if not self.object.last_evidence:
            raise Http404
        if self.object.owner != self.request.user.institution:
            raise Http403

        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        self.object.initial()
        lot_tags = LotTag.objects.filter(owner=self.request.user.institution)
        dpps = []
        if settings.DPP:
            dpps = Proof.objects.filter(
                uuid__in=self.object.uuids,
                type=PROOF_TYPE["IssueDPP"]
            )
        context.update({
            'object': self.object,
            'snapshot': self.object.get_last_evidence(),
            'lot_tags': lot_tags,
            'dpps': dpps,
        })
        return context


class PublicDeviceWebView(TemplateView):
    template_name = "device_web.html"

    def get(self, request, *args, **kwargs):
        self.object = Device(id=kwargs['pk'])

        if not self.object.last_evidence:
            raise Http404

        if self.request.headers.get('Accept') == 'application/json':
            json_response = self.create_json_response(
                self.request.user.is_authenticated)
            return json_response
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        self.object.initial()
        context.update({
            'object': self.object
        })
        return context

    def create_json_response(self, is_user_authenticated):
        device_data = self.object.get_device_data(is_user_authenticated)
        return JsonResponse(device_data)


class AddUserPropertyView(DashboardView, CreateView):
    template_name = "new_user_property.html"
    title = _("New User Property")
    breadcrumb = "Device / New Property"
    success_url = reverse_lazy('dashboard:unassigned_devices')
    model = UserProperty
    fields = ("key", "value")

    def form_valid(self, form):
        form.instance.owner = self.request.user.institution
        form.instance.user = self.request.user
        form.instance.uuid = self.annotation.uuid
        form.instance.type = Property.Type.USER
        response = super().form_valid(form)
        return response

    def get_form_kwargs(self):
        pk = self.kwargs.get('pk')
        institution = self.request.user.institution
        self.annotation = SystemProperty.objects.filter(
            owner=institution,
            value=pk,
            type=Property.Type.SYSTEM
        ).first()

        if not self.annotation:
            raise Http404

        self.success_url = reverse_lazy('device:details', args=[pk])
        kwargs = super().get_form_kwargs()
        return kwargs

class DeleteUserPropertyView(DashboardView, DeleteView):
    model = UserProperty

    def post(self, request, *args, **kwargs):
        self.pk = kwargs['pk']
        referer = request.META.get('HTTP_REFERER')
        if not referer:
            raise Http404("No referer header found")

        self.object = get_object_or_404(
            self.model,
            pk=self.pk,
            owner=self.request.user.institution
        )
        self.object.delete()
        messages.success(self.request, _("User property deleted successfully."))

        # Redirect back to the original URL
        return redirect(referer)    


class AddDocumentView(DashboardView, CreateView):
    template_name = "new_annotation.html"
    title = _("New Document")
    breadcrumb = "Device / New document"
    success_url = reverse_lazy('dashboard:unassigned_devices')
    model = SystemProperty
    fields = ("key", "value")

    def form_valid(self, form):
        form.instance.owner = self.request.user.institution
        form.instance.user = self.request.user
        form.instance.uuid = self.annotation.uuid
        form.instance.type = Property.Type.DOCUMENT
        response = super().form_valid(form)
        return response

    def get_form_kwargs(self):
        pk = self.kwargs.get('pk')
        institution = self.request.user.institution
        self.annotation = SystemProperty.objects.filter(
            owner=institution,
            value=pk,
            type=Property.Type.SYSTEM
        ).first()

        if not self.annotation:
            raise Http404

        self.success_url = reverse_lazy('device:details', args=[pk])
        kwargs = super().get_form_kwargs()
        return kwargs
