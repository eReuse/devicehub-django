import json
import logging

from django.http import JsonResponse
from django.conf import settings
from django.db import IntegrityError
from django.urls import reverse_lazy
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, Http404, render
from django.db import transaction
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
from environmental_impact.algorithms.algorithm_factory import FactoryEnvironmentImpactAlgorithm
from evidence.models import UserProperty, SystemProperty, Evidence
from lot.models import LotTag
from device.models import Device
from device.forms import DeviceMainForm, DeviceAttributeFormSet, save_device_data

from evidence.models import SystemProperty, RootAlias
from evidence.tables import EvidenceTable
from django_tables2 import RequestConfig
if settings.DPP:
    from dpp.models import Proof
    from dpp.api_dlt import PROOF_TYPE


logger = logging.getLogger(__name__)


class DeviceLogMixin(DashboardView):

    def log_registry(self, _uuid, msg):
        DeviceLog.objects.create(
            snapshot_uuid=_uuid,
            event=msg,
            user=self.request.user,
            institution=self.request.user.institution
        )

class NewDeviceView(DashboardView, FormView):
    template_name = "new_device.html"
    form_class = DeviceMainForm
    success_url = reverse_lazy('dashboard:unassigned')
    title = _("New Device")
    breadcrumb = "Device / New Device"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        if self.request.POST:
            context['attribute_formset'] = DeviceAttributeFormSet(self.request.POST)
        else:
            context['attribute_formset'] = DeviceAttributeFormSet()

        context['subtitle'] = self.title
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        attribute_formset = context['attribute_formset']

        if not attribute_formset.is_valid():
            return self.render_to_response(context)
        form.save(attribute_formset=attribute_formset)

        return super().form_valid(form)


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


class DetailsView(DashboardView, TemplateView ):
    template_name = "details.html"
    title = _("Device")
    breadcrumb = "Device / Details"
    table_class = EvidenceTable

    def get(self, request, *args, **kwargs):
        self.pk = kwargs['pk']
        self.object = Device(id=self.pk, owner=self.request.user.institution)
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
            _dpps = Proof.objects.filter(
                uuid__in=self.object.uuids,
                type=PROOF_TYPE["IssueDPP"]
            )
            for x in _dpps:
                dpp = "{}:{}".format(self.pk, x.signature)
                dpps.append((dpp, x.signature[:10], x))
        # TODO Specify algorithm via dropdown, if not specified, use default.
        try:
            enviromental_impact_algorithm = FactoryEnvironmentImpactAlgorithm.run_environmental_impact_calculation()
            enviromental_impact = enviromental_impact_algorithm.get_device_environmental_impact(
            self.object)
        except Exception as err:
            logger.error("Enviromental Impact: {}".format(err))
            enviromental_impact = None
        last_evidence = self.object.get_last_evidence()
        uuids = self.object.uuids

        ev_queryset = Evidence.get_device_evidences(self.request.user, uuids)
        evidence_table = EvidenceTable(ev_queryset, exclude =('device', ))

        RequestConfig(self.request).configure(evidence_table)

        state_definitions = StateDefinition.objects.filter(
            institution=self.request.user.institution
        ).order_by('order')
        device_states = State.objects.filter(snapshot_uuid__in=uuids).order_by('-date')
        device_logs = DeviceLog.objects.filter(
            snapshot_uuid__in=uuids).order_by('-date')
        device_notes = Note.objects.filter(snapshot_uuid__in=uuids).order_by('-date')
        context.update({
            'object': self.object,
            'snapshot': last_evidence,
            'lot_tags': lot_tags,
            'dpps': dpps,
            'impact': enviromental_impact,
            "state_definitions": state_definitions,
            "device_states": device_states,
            "device_logs": device_logs,
            "device_notes": device_notes,
            "table": evidence_table,
        })
        return context


class PublicDeviceWebView(TemplateView):
    template_name = "device_web.html"

    def get(self, request, *args, **kwargs):
        self.pk = kwargs['pk']
        self.object = Device(id=self.pk)
        owner = self.get_owner_for_device(self.pk)

        if not owner:
            raise Http404("Device ID not recognized")

        self.object = Device(id=self.pk, owner=owner)
        self.object.initial()

        if not self.object.get_last_evidence():
            raise Http404

        if self.request.headers.get('Accept') == 'application/json':
            return self.get_json_response()
        return super().get(request, *args, **kwargs)

    def get_owner_for_device(self, pk):
        prop = SystemProperty.objects.filter(value=pk).select_related('owner').first()
        if prop:
            return prop.owner

        alias = RootAlias.objects.filter(root=pk).select_related('owner').first()
        if alias:
            return alias.owner

        return None

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
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


class AddUserPropertyView(DeviceLogMixin, CreateView):
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

        try:
            response = super().form_valid(form)
            messages.success(self.request, _("Property successfully added."))
            log_message = _("<Created> UserProperty: {}: {}".format(
                form.instance.key,
                form.instance.value
            ))

            self.log_registry(form.instance.uuid, log_message)
            return response
        except IntegrityError:
            messages.error(self.request, _("Property is already defined."))
            return self.form_invalid(form)

    def get_form_kwargs(self):
        pk = self.kwargs.get('pk')
        institution = self.request.user.institution
        self.property = SystemProperty.objects.filter(
            owner=institution, value=pk).first()
        if not self.property:
            raise Http404

        return super().get_form_kwargs()

    def get_success_url(self):
        pk = self.kwargs.get('pk')
        return reverse_lazy('device:details', args=[pk]) + "#user_properties"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['pk'] = self.kwargs.get('pk')
        return context


class UpdateUserPropertyView(DeviceLogMixin, UpdateView):
    template_name = "new_user_property.html"
    title = _("Update User Property")
    breadcrumb = "Device / Update Property"
    model = UserProperty
    fields = ("key", "value")

    def get_form_kwargs(self):
        pk = self.kwargs.get('pk')
        institution = self.request.user.institution
        self.object = get_object_or_404(UserProperty, owner=institution, pk=pk)
        self.old_key = self.object.key
        self.old_value = self.object.value
        return super().get_form_kwargs()

    def form_valid(self, form):
        new_key = form.cleaned_data['key']
        new_value = form.cleaned_data['value']

        try:
            super().form_valid(form)
            messages.success(self.request, _("Property updated successfully."))
            log_message = _("<Updated> UserProperty: {}: {} to {}: {}".format(
                self.old_key,
                self.old_value,
                new_key,
                new_value
            ))
            self.log_registry(form.instance.uuid, log_message)
            # return response
            return redirect(self.get_success_url())
        except IntegrityError:
            messages.error(self.request, _("Property is already defined."))
            return self.form_invalid(form)

    def form_invalid(self, form):
        super().form_invalid(form)
        return redirect(self.get_success_url())

    def get_success_url(self):
        pk = self.kwargs.get('device_id')
        return reverse_lazy('device:details', args=[pk]) + "#user_properties"


class DeleteUserPropertyView(DeviceLogMixin, DeleteView):
    model = UserProperty

    def get_queryset(self):
        return UserProperty.objects.filter(owner=self.request.user.institution)

    #using post() method because delete() method from DeleteView has some issues
    # with messages framework
    def post(self, request, *args, **kwargs):
        pk = self.kwargs.get('pk')
        institution = self.request.user.institution
        self.object = get_object_or_404(UserProperty, owner=institution, pk=pk)
        self.object.delete()

        msg = _("<Deleted> User Property: {}:{}".format(
            self.object.key,
            self.object.value
        ))
        self.log_registry(self.object.uuid, msg)
        messages.info(self.request, _("User property deleted successfully."))

        return redirect(self.get_success_url())

    def get_success_url(self):
        pk = self.kwargs.get('device_id')
        return reverse_lazy('device:details', args=[pk]) + "#user_properties"
