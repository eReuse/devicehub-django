import json
import logging
import requests
import re

from django.http import JsonResponse
from django.conf import settings
from django.db import IntegrityError
from django.urls import reverse_lazy
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, Http404
from django.utils.translation import gettext_lazy as _
from django.urls import reverse
from django.views.generic.edit import (
    View,
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
from user.models import InstitutionSettings
from lot.models import LotTag
from device.models import Device
from device.forms import DeviceFormSet
from evidence.models import SystemProperty, CredentialProperty
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
    title = _("New Device")
    breadcrumb = "Device / New Device"
    success_url = reverse_lazy('dashboard:unassigned')
    form_class = DeviceFormSet

    def form_valid(self, form):
        form.save(self.request.user)
        response = super().form_valid(form)
        return response

    def form_invalid(self, form):
        response = super().form_invalid(form)
        return response


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
            # If total usage time is 0, treat as unavailable data
            if (enviromental_impact and
                    enviromental_impact.relevant_input_data.get(
                        'total_usage_time', 0) == 0):
                enviromental_impact = None
        except Exception as err:
            logger.error("Environmental Impact Error: {}".format(err))
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


class IssueDigitalPassportView(DeviceLogMixin, View):
    def get(self, request, *args, **kwargs):
        pk = self.kwargs.get('device_id')
        device = Device(id=pk)
        last_evidence = device.last_evidence

        institution_config = InstitutionSettings.objects.get(institution=self.request.user.institution)

        API_ENDPOINT = getattr(institution_config, "signing_service_domain", "https://cloudy5.pc.ac.upc.edu/api/v1/issue-credential/")
        API_KEY = getattr(institution_config, "signing_auth_token", "970a6c32-4829-4863-b80a-0a351a6a892f")
        PASSPORT_SCHEMA = getattr(institution_config, "device_dpp_schema", "ICTGoodsPassport_UNTP_schema_v1.json")

        def convert_ram_to_mb(ram_string):
            if not isinstance(ram_string, str): return 0
            match = re.match(r'(\d+\.?\d*)\s*(GiB|MiB|GB|MB)', ram_string, re.IGNORECASE)
            if not match: return 0
            value, unit = float(match.groups()[0]), match.groups()[1].lower()
            if 'gib' in unit: return int(value * 1024)
            if 'gb' in unit: return int(value * 1000)
            if 'mib' in unit or 'mb' in unit: return int(value)
            return 0

        components = device.components_export()
        characteristics = {
            "chassis": components.get('type') or "Laptop",
            "manufacturer": components.get('manufacturer') or "Unknown",
            "model": components.get('model') or "Unknown",
            "cpu_model": components.get('cpu_model'),
            "cpu_cores": components.get('cpu_cores'),
            "current_state": components.get('current_state') or "refurbished",
            "ram_total": convert_ram_to_mb(components.get('ram_total')),
            "ram_type": components.get('ram_type') or "Other",
            "ram_slots": components.get('ram_slots'),
            "slots_used": components.get('slots_used'),
            "drive": components.get('drive') or "Other",
            "gpu_model": components.get('gpu_model'),
            "user_properties": components.get('user_properties'),
            "serial": components.get('serial')
        }
        characteristics = {k: v for k, v in characteristics.items() if v is not None and v != ''}

        credential_subject = {
            "type": ["ProductPassport"],
            "id": f"urn:uuid:{device.id}",
            "product": {
                "type": ["Product"],
                "id": f"urn:ereuse:device:{device.id}",
                "name": f"{components.get('manufacturer', 'Unknown')} {components.get('model', 'Unknown')}",
                "description": "A personal refurbished computing device.",
                "serialNumber": components.get('serial'),
                "characteristics": characteristics
            }
        }

        service_endpoint = request.build_absolute_uri(
            reverse('evidence:credential_by_evidence', kwargs={'uuid': last_evidence.uuid})
        )
        payload = {
            "schema_name": PASSPORT_SCHEMA,
            "create_did": True,
            "credentialSubject": credential_subject,
            "service_endpoint": service_endpoint
        }

        headers = {
            'Authorization': f'Bearer {API_KEY}',
            'Content-Type': 'application/json'
        }

        try:
            response = requests.post(
                API_ENDPOINT,
                json=payload,
                headers=headers,
                timeout=15,
                verify=False,
                allow_redirects=False
            )
            response.raise_for_status()

            signed_credential = response.json()
            credential_id = signed_credential.get('id')

            if credential_id:
                last_evidence = device.last_evidence
                if not last_evidence or not last_evidence.uuid:
                    messages.error(self.request, "Could not save passport: Device is missing evidence or the evidence has no UUID.")
                    return redirect('device:details', pk=pk)

                credential= CredentialProperty.objects.create(
                    uuid=last_evidence.uuid,
                    key="DigitalProductPassport",
                    value=credential_id or 'N/A',
                    credential=signed_credential,
                    owner=request.user.institution if hasattr(request.user, 'institution') else 'Default Owner',
                    user=request.user
                )
                log_message = f"Digital Passport issued successfully. Credential/subject ID: {credential_id}"
                messages.success(self.request, log_message)
            else:
                 messages.warning(self.request, "API returned a success status but no credential ID.")

        except requests.exceptions.HTTPError as http_err:
            status_code = http_err.response.status_code
            error_message = self._get_api_error_message(http_err.response)
            logger.warning(f"API HTTP error {status_code} for device {pk}: {error_message}")

            if status_code == 400:
                messages.error(self.request, f"Failed to issue passport. The data was invalid. {error_message}")
            elif status_code == 409:
                messages.warning(self.request, "A digital passport already exists for this device's evidence log.")
            elif status_code == 422:
                messages.error(self.request, f"Configuration Error: The schema '{PASSPORT_SCHEMA}' was not found on the API server. Please contact an administrator.")
            elif status_code == 500:
                messages.error(self.request, f"Failed to issue passport: The remote API server failed due to a configuration error. Please contact an administrator. {error_message}")
            else:
                messages.error(self.request, f"An unexpected API error occurred. {error_message}")

        except requests.exceptions.ConnectionError:
            logger.error(f"API ConnectionError for device {pk}: Could not connect to {API_ENDPOINT}")
            messages.error(self.request, f"Network Error: Could not connect to the passport service at {API_ENDPOINT}.")
        except requests.exceptions.Timeout:
            logger.warning(f"API Timeout for device {pk} at {API_ENDPOINT}")
            messages.error(self.request, "Network Error: The request to the passport service timed out.")
        except requests.exceptions.RequestException as err:
            logger.error(f"API RequestException for device {pk}: {err}", exc_info=True)
            messages.error(self.request, f"An API request error occurred: {err}")
        except Exception as e:
            logger.error(f"Unexpected local error issuing passport for device {pk}: {e}", exc_info=True)
            messages.error(self.request, f"An unexpected local error occurred: {e}")

        return redirect('device:details', pk=pk)

    def _get_api_error_message(self, response: requests.Response):
        try:
            error_data = response.json()
            server_error = error_data.get('error', 'Unknown server error')
            details = error_data.get('details')
            path = error_data.get('path')

            message = f"API Error: {server_error}"
            if details:
                message += f" Details: {details}"
            if path:
                message += f" (Field: {''.join(['[' + str(p) + ']' if isinstance(p, int) else '.' + p for p in path]).lstrip('.')})"
            return message
        except json.JSONDecodeError:
            return f"API Error ({response.status_code}): {response.text[:250]}..."
