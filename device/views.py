import json
import logging
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
from action.models import StateDefinition, State, DeviceLog, Note
from dashboard.mixins import DashboardView, Http403
from evidence.models import UserProperty, SystemProperty
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
        last_evidence= self.object.get_last_evidence(),
        uuid=self.object.last_uuid()
        state_definitions = StateDefinition.objects.filter(
            institution=self.request.user.institution
        ).order_by('order')
        context.update({
            'object': self.object,
            'snapshot': last_evidence,
            'lot_tags': lot_tags,
            'dpps': dpps,
            "state_definitions": state_definitions,
            "device_states": State.objects.filter(snapshot_uuid=uuid).order_by('-date'),
            "device_logs": DeviceLog.objects.filter(snapshot_uuid=uuid).order_by('-date'),
            "device_notes": Note.objects.filter(snapshot_uuid=uuid).order_by('-date'),
        })
        return context


class PublicDeviceWebView(TemplateView):
    template_name = "device_web.html"

    def get(self, request, *args, **kwargs):
        self.pk = kwargs['pk']
        self.object = Device(id=self.pk)

        if not self.object.last_evidence:
            raise Http404

        if self.request.headers.get('Accept') == 'application/json':
            return self.get_json_response()
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        self.object.initial()
        context.update({
            'object': self.object
        })
        return context

    @property
    def public_fields(self):
        return {
            'id': self.object.id,
            'shortid': self.object.shortid,
            'uuids': self.object.uuids,
            'hids': self.object.hids,
            'components': self.remove_serial_number_from(self.object.components),
        }

    @property
    def authenticated_fields(self):
        return {
            'serial_number': self.object.serial_number,
            'components': self.object.components,
        }

    def remove_serial_number_from(self, components):
        for component in components:
            if 'serial_number' in component:
                del component['SerialNumber']
        return components

    def get_device_data(self):
        data = self.public_fields
        if self.request.user.is_authenticated:
            data.update(self.authenticated_fields)
        return data

    def get_json_response(self):
        device_data = self.get_device_data()
        return JsonResponse(device_data)


class AddUserPropertyView(DashboardView, CreateView):
    template_name = "new_user_property.html"
    title = _("New User Property")
    breadcrumb = "Device / New Property"
    model = UserProperty
    fields = ("key", "value")

    def form_valid(self, form):
        form.instance.owner = self.request.user.institution
        form.instance.user = self.request.user
        form.instance.uuid = self.property.uuid
        form.instance.type = UserProperty.Type.USER

        message = _("<Created> UserProperty: {}: {}".format(form.instance.key, form.instance.value))
        DeviceLog.objects.create(
            snapshot_uuid=form.instance.uuid,
            event=message,
            user=self.request.user,
            institution=self.request.user.institution
        )

        messages.success(self.request, _("User property successfully added."))
        response = super().form_valid(form)
        return response

    def get_form_kwargs(self):
        pk = self.kwargs.get('pk')
        institution = self.request.user.institution
        self.property = get_object_or_404(SystemProperty, owner=institution, value=pk)

        return super().get_form_kwargs()

    def get_success_url(self):
        return reverse_lazy('device:details', args=[self.kwargs.get('pk')])


class UpdateUserPropertyView(DashboardView, UpdateView):
    template_name = "new_user_property.html"
    title = _("Update User Property")
    breadcrumb = "Device / Update Property"
    model = UserProperty
    fields = ("key", "value")

    def get_queryset(self):
        pk = self.kwargs.get('pk')
        institution = self.request.user.institution
        return UserProperty.objects.filter(pk=pk, owner=institution)

    def form_valid(self, form):

        old_instance = self.get_object()
        old_key = old_instance.key
        old_value = old_instance.value

        form.instance.owner = self.request.user.institution
        form.instance.user = self.request.user
        form.instance.type = UserProperty.Type.USER

        new_key = form.cleaned_data['key']
        new_value = form.cleaned_data['value']

        message = _("<Updated> UserProperty: {}: {} to {}: {}".format(old_key, old_value, new_key, new_value))
        DeviceLog.objects.create(
            snapshot_uuid=form.instance.uuid,
            event=message,
            user=self.request.user,
            institution=self.request.user.institution
        )

        messages.success(self.request, _("User property updated successfully."))
        return super().form_valid(form)

    def get_success_url(self):
        return self.request.META.get('HTTP_REFERER', reverse_lazy('device:details', args=[self.object.pk]))


class DeleteUserPropertyView(DashboardView, DeleteView):
    model = UserProperty

    def get_queryset(self):
        return UserProperty.objects.filter(owner=self.request.user.institution)

    #using post() method because delete() method from DeleteView has some issues with messages framework
    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        self.object.delete()

        message = _("<Deleted> User Property: {}:{}".format(self.object.key, self.object.value ))
        DeviceLog.objects.create(
            snapshot_uuid=self.object.uuid,
            event=message,
            user=self.request.user,
            institution=self.request.user.institution
        )

        messages.info(self.request, _("User property deleted successfully."))

        return self.handle_success()

    def handle_success(self):
        return redirect(self.get_success_url())

    def get_success_url(self):
        return self.request.META.get('HTTP_REFERER', reverse_lazy('device:details', args=[self.object.pk]))

class AddDocumentView(DashboardView, CreateView):
    template_name = "new_user_property.html"
    title = _("New Document")
    breadcrumb = "Device / New document"
    success_url = reverse_lazy('dashboard:unassigned_devices')
    model = UserProperty
    fields = ("key", "value")

    def form_valid(self, form):
        form.instance.owner = self.request.user.institution
        form.instance.user = self.request.user
        form.instance.uuid = self.property.uuid
        form.instance.type = UserProperty.Type.DOCUMENT
        response = super().form_valid(form)
        return response

    def get_form_kwargs(self):
        pk = self.kwargs.get('pk')
        institution = self.request.user.institution
        self.property = SystemProperty.objects.filter(
            owner=institution,
            value=pk,
        ).first()

        if not self.property:
            raise Http404

        self.success_url = reverse_lazy('device:details', args=[pk])
        kwargs = super().get_form_kwargs()
        return kwargs
