import logging
import re

from collections import defaultdict
from dateutil.parser import isoparse
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
from lot.models import LotTag
from device.models import Device
from device.forms import DeviceFormSet
from evidence.models import SystemProperty, CredentialProperty
from evidence.tables import EvidenceTable, CredentialTable
from django_tables2 import RequestConfig
from evidence.services import CredentialService
if settings.DPP:
    from dpp.models import Proof
    from dpp.api_dlt import PROOF_TYPE


from django.utils import timezone 
from dateutil.parser import isoparse


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

        credential_queryset = CredentialProperty.objects.filter(
            uuid__in=uuids,
            owner=self.request.user.institution
        ).order_by('-created')
        credential_table = CredentialTable(credential_queryset)
        RequestConfig(self.request, paginate={'per_page': 10}).configure(credential_table)


        context['dismantle_form'] = DeviceFormSet()
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
            "credential_table": credential_table,
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
        try:
            device = Device(id=pk, owner=request.user.institution)
            device.initial()
        except Exception:
             messages.error(request, "Device not found.")
             return redirect('device:list')

        last_evidence = device.last_evidence
        if not last_evidence:
            messages.error(request, "Cannot issue Passport: No evidence found for this device.")
            return redirect('device:details', pk=pk)

        service = CredentialService(request.user)
        dpp_endpoint = request.build_absolute_uri(
            reverse('device:full_dpp', kwargs={'device_id': device.id})
        )
        did_error = service.ensure_device_did(device, service_endpoint=dpp_endpoint)
        did_warning_message = None
        if did_error:
            error_lower = did_error.lower()
            if  "[404]" in error_lower:
                did_warning_message = "Passport issued but service endpoint not modified given that you don't own the DID."
            else:
                messages.error(request, f"Failed to issue Passport. DID configuration error: {did_error}")
                return redirect('device:details', pk=pk)

        def convert_ram_to_mb(ram_string):
            if not isinstance(ram_string, str): return 0
            match = re.match(r'(\d+\.?\d*)\s*(GiB|MiB|GB|MB)', ram_string, re.IGNORECASE)
            if not match: return 0
            value, unit = float(match.groups()[0]), match.groups()[1].lower()
            if 'gib' in unit: return int(value * 1024)
            if 'gb' in unit: return int(value * 1000)
            if 'mib' in unit or 'mb' in unit: return int(value)
            return 0

        components = device.components_export() or {}
        raw_characteristics = {
            "chassis": components.get('type') or "Laptop",
            "manufacturer": components.get('manufacturer') or "Unknown",
            "model": components.get('model') or "Unknown",
            "cpu_model": components.get('cpu_model'),
            "cpu_cores": str(components.get('cpu_cores')) if components.get('cpu_cores') else None,
            "current_state": components.get('current_state') or "refurbished",
            "ram_total": convert_ram_to_mb(components.get('ram_total')),
            "ram_type": components.get('ram_type') or "Other",
            "ram_slots": components.get('ram_slots'),
            "slots_used": components.get('slots_used'),
            "drive": components.get('drive') or "Other",
            "gpu_model": components.get('gpu_model'),
            "user_properties": components.get('user_properties'),
            "serial": components.get('serial', "NA")
        }
        characteristics = {k: v for k, v in raw_characteristics.items() if v is not None and v != ''}

        device_uri = device.did if device.did else f"ereuse:{device.id}"
        traceability_info = self._get_traceability_info(device, request)
        credential_subject = {
            "type": ["ProductPassport"],
            "id": device_uri,
            "product": {
                "type": ["Product"],
                "id": device_uri,
                "name": f"{components.get('manufacturer', 'Unknown')} {components.get('model', 'Unknown')}",
                "description": "A personal refurbished computing device.",
                "serialNumber": components.get('serial'),
                "characteristics": characteristics
            },
            "traceabilityInformation": traceability_info
        }

        credential, error = service.issue_device_credential(
            credential_type_key='dpp',
            credential_subject=credential_subject,
            credential_db_key='DigitalProductPassport',
            device=device,
            uuid=last_evidence.uuid,
            description="Digital Product Passport"
        )

        if error:
            messages.error(request, error)
        else:
            if did_warning_message:
                messages.warning(request, did_warning_message)
            else:
                messages.success(request, "Digital Product Passport issued successfully!")

        return redirect('device:details', pk=pk)


    def _get_facility_info(self, device):
        facility_cred_prop = CredentialProperty.objects.filter(
            owner=device.owner,
            key='DigitalFacilityRecord'
        ).order_by('-created').first()

        if not facility_cred_prop:
            return None

        subject = facility_cred_prop.credential.get('credentialSubject', {})
        facility_data = subject.get('facility', subject)

        return {
            "id": facility_data.get("id"),
            "name": facility_data.get("name"),
            "registeredId": facility_data.get("registeredId", ""),
            "idScheme": {
                "type": ["IdentifierScheme"],
                "id": "https://www.gleif.org/lei/",
                "name": "Legal Entity Identifier"
            }
        }

    def _get_traceability_info(self, device, request):
        events = CredentialProperty.objects.filter(
            uuid__in=device.uuids,
            key='DigitalTraceabilityEvent',
        ).order_by('created')

        if not events:
            return []

        grouped = defaultdict(list)

        for prop in events:
            subject = prop.credential.get('credentialSubject', [])
            if isinstance(subject, dict):
                subject = [subject]

            for event in subject:
                raw_process = event.get('processType', 'Unknown')
                process_name = raw_process.split(':')[-1].capitalize() if ':' in raw_process else raw_process

                cred_url = request.build_absolute_uri(
                    reverse('evidence:credential_detail', kwargs={'pk': prop.id})
                )

                link_obj = {
                    "type": ["SecureLink", "Link"],
                    "linkURL": cred_url,
                    "linkName": f"Traceability Event - {process_name}",
                    "linkType": "application/json",
                }

                grouped[process_name].append(link_obj)

        traceability_information = []

        for process, links in grouped.items():
            entry = {
                "type": ["TraceabilityPerformance"],
                "valueChainProcess": process,
                "verifiedRatio": 1.0,
                "traceabilityEvent": links
            }
            traceability_information.append(entry)

        return traceability_information


class DeviceFullDPPView(DashboardView, TemplateView):
    template_name = "device_dpp.html"

    def get(self, request, *args, **kwargs):
        self.pk = kwargs.get('device_id')
        try:
            self.device = Device(id=self.pk, owner=self.request.user.institution)
        except Exception:
            raise Http404("Device not found")

        if not self.device.last_evidence:
            raise Http404("No evidence found for this device.")
        if self.device.owner != self.request.user.institution:
            raise Http403("You do not have permission to view this device.")

        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        pk = self.kwargs.get('device_id')
        device = Device(id=pk, owner=self.request.user.institution)
        device.initial()

        all_device_creds = CredentialProperty.objects.filter(
            uuid__in=device.uuids,
            owner=self.request.user.institution
        ).order_by('-created')

        latest_dpp_cred = all_device_creds.filter(key='DigitalProductPassport').first()
        dpp_data = None

        if latest_dpp_cred:
            subject = latest_dpp_cred.credential.get('credentialSubject', {})
            if isinstance(subject, dict):
                dpp_data = subject.get('product') or subject.get('facility')
                if not dpp_data and 'name' in subject:
                    dpp_data = subject

        timeline_events = []
        traceability_creds = all_device_creds.filter(key__in=['DigitalTraceabilityEvent', 'TraceabilityBatch'])

        for cred in traceability_creds:
            events_list = cred.credential.get('credentialSubject', [])
            if isinstance(events_list, dict):
                events_list = [events_list]
            elif not isinstance(events_list, list):
                events_list = []

            for event in events_list:
                event['meta_verified_id'] = cred.credential.get('id')
                event['meta_verified_at'] = cred.created
                event['meta_verified_pk'] = cred.pk

                raw_time = event.get('eventTime')

                if raw_time:
                    try:
                        dt = isoparse(raw_time)
                    except (ValueError, TypeError):
                        dt = cred.created
                else:
                    dt = cred.created

                if timezone.is_naive(dt):
                    dt = timezone.make_aware(dt)

                event['parsed_date'] = dt
                timeline_events.append(event)

        timeline_events.sort(key=lambda x: x['parsed_date'], reverse=True)

        latest_facility_cred = CredentialProperty.objects.filter(
            owner=device.owner,
            key='DigitalFacilityRecord'
        ).order_by('-created').first()

        facility_data = None
        if latest_facility_cred:
            subject = latest_facility_cred.credential.get('credentialSubject', {})
            facility_data = subject.get('facility') or subject

        context.update({
            'device': device,

            # DPP Data
            'dpp_meta': latest_dpp_cred,
            'dpp_data': dpp_data,

            # Facility Data
            'facility_meta': latest_facility_cred,
            'facility_data': facility_data,

            # Timeline
            'events': timeline_events,
        })
        return context
