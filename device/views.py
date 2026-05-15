import logging
import re

from django.db.models import Q
from collections import defaultdict
from dateutil.parser import isoparse
from django.http import JsonResponse
from django.conf import settings
from django.db import IntegrityError, models
from django.urls import reverse_lazy, resolve
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, Http404, render
from django.db import transaction
from django.utils.translation import gettext_lazy as _
from django.urls import reverse
from django.views.generic.edit import (
    View,
    CreateView,
    UpdateView,
    FormView,
    DeleteView,
)
from django.views.generic import ListView

from django.views.generic.base import TemplateView
from action.models import StateDefinition, State, DeviceLog, Note
from dashboard.mixins import DashboardView, Http403
from environmental_impact.algorithms.algorithm_factory import FactoryEnvironmentImpactAlgorithm
from evidence.models import UserProperty, SystemProperty, Evidence, RootAlias
from lot.models import LotTag
from device.models import Device
from evidence.models import SystemProperty, RootAlias, CredentialProperty
from device.forms import DeviceAttributeFormSet, DeviceMainForm, DEVICE_ATTRIBUTE_SUGGESTIONS
from device.forms import DeviceFormSet
from evidence.tables import EvidenceTable, CredentialTable
from django_tables2 import RequestConfig
from user.models import InstitutionSettings
from evidence.services import CredentialService
if settings.DPP:
    from dpp.models import Proof
    from dpp.api_dlt import PROOF_TYPE


from django.utils import timezone 
from dateutil.parser import isoparse


logger = logging.getLogger(__name__)


class CosmeticGrade(models.TextChoices):
    GRADE_A = 'GradeA', _('Grade A - Excellent (Like New)')
    GRADE_B = 'GradeB', _('Grade B - Good (Minor Scratches)')
    GRADE_C = 'GradeC', _('Grade C - Fair (Noticeable Wear)')
    GRADE_D = 'GradeD', _('Grade D - Poor (Heavy Wear/Damaged)')

class DeviceLogMixin(DashboardView):

    def log_registry(self, _uuid, msg):
        DeviceLog.objects.create(
            snapshot_uuid=_uuid,
            event=msg,
            user=self.request.user,
            institution=self.request.user.institution
        )

    def latest_uuid_for_device(self, institution, device_id):
        """Return the most recent snapshot uuid for a device, for DeviceLog only.

        DeviceLog is still anchored to a snapshot uuid — will migrate in Phase 5.
        """
        physicals = RootAlias.physical_aliases(institution, device_id)
        prop = SystemProperty.objects.filter(
            owner=institution, value__in=physicals
        ).order_by("-created").first()
        return prop.uuid if prop else None

class NewDeviceView(DashboardView, FormView):
    template_name = "new_device.html"
    success_url = reverse_lazy('dashboard:unassigned')
    title = _("New Device")
    breadcrumb = [(_("Device"), reverse_lazy("dashboard:all_device")), (_("New Device"), None)]
    success_url = reverse_lazy('dashboard:unassigned')
    form_class = DeviceMainForm

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

        suggestions_for_js = {}
        for dev_type, attrs in DEVICE_ATTRIBUTE_SUGGESTIONS.items():
            suggestions_for_js[dev_type] = [
                {"name": a["name"], "label": str(a["label"])} for a in attrs
            ]
        context['device_suggestions'] = suggestions_for_js

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
    breadcrumb = [(_("Device"), reverse_lazy("dashboard:all_device")), (_("Update Device"), None)]
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
    breadcrumb = [(_("Device"), reverse_lazy("dashboard:all_device")), (_("Details"), None)]
    table_class = EvidenceTable

    def get(self, request, *args, **kwargs):
        self.pk = kwargs['pk']
        root = RootAlias.objects.filter(
            owner=self.request.user.institution,
            alias=self.pk
        ).first()

        if root and root.root != self.pk:
            return redirect(reverse_lazy('device:details', args=[root.root]))

        self.object = Device(id=self.pk, owner=self.request.user.institution)
        if not self.object.last_evidence:
            raise Http404
        if self.object.owner != self.request.user.institution:
            raise Http403

        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        url = request.POST.get("url")

        if url:
            dev_ids = request.POST.getlist("devices")
            request.session["devices"] = dev_ids
            request.session.modified = True

            try:
                resource = resolve(url)
                if resource:
                    return redirect(url)
            except Exception:
                pass

        return self.get(request, *args, **kwargs)

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
    breadcrumb = [(_("Device"), reverse_lazy("dashboard:all_device")), (_("New Property"), None)]
    model = UserProperty
    fields = ("key", "value")

    def form_valid(self, form):
        institution = self.request.user.institution
        form.instance.owner = institution
        form.instance.user = self.request.user
        form.instance.device_id = RootAlias.resolve_root(institution, self.kwargs['pk'])
        form.instance.type = UserProperty.Type.USER

        try:
            response = super().form_valid(form)
            messages.success(self.request, _("Property successfully added."))
            log_message = _("<Created> UserProperty: {}: {}".format(
                form.instance.key,
                form.instance.value
            ))
            # DeviceLog is still anchored to a snapshot uuid — will migrate in Phase 5.
            log_uuid = self.latest_uuid_for_device(institution, form.instance.device_id)
            if log_uuid:
                self.log_registry(log_uuid, log_message)
            return response
        except IntegrityError:
            messages.error(self.request, _("Property is already defined."))
            return self.form_invalid(form)

    def get_form_kwargs(self):
        pk = self.kwargs.get('pk')
        institution = self.request.user.institution
        # A device may be known as an alias (physical id) or as a root
        # (custom_id set via set_alias, which has no self-referential row).
        if not RootAlias.objects.filter(owner=institution).filter(
            Q(alias=pk) | Q(root=pk)
        ).exists():
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
    breadcrumb = [(_("Device"), reverse_lazy("dashboard:all_device")), (_("Update Property"), None)]
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
            # DeviceLog is still anchored to a snapshot uuid — will migrate in Phase 5.
            institution = self.request.user.institution
            log_uuid = self.latest_uuid_for_device(institution, form.instance.device_id)
            if log_uuid:
                self.log_registry(log_uuid, log_message)
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
        # DeviceLog is still anchored to a snapshot uuid — will migrate in Phase 5.
        institution = self.request.user.institution
        log_uuid = self.latest_uuid_for_device(institution, self.object.device_id)
        if log_uuid:
            self.log_registry(log_uuid, msg)
        messages.info(self.request, _("User property deleted successfully."))

        return redirect(self.get_success_url())

    def get_success_url(self):
        pk = self.kwargs.get('device_id')
        return reverse_lazy('device:details', args=[pk]) + "#user_properties"


class DeviceBulkLabelView(DashboardView, ListView):
    model = Device
    template_name = 'bulk_labels.html'
    context_object_name = 'devices'

    def get(self, request, *args, **kwargs):
        self.single_pk = self.kwargs.get('pk')

        if self.single_pk:
            self.selected_devices = [Device(id=self.single_pk)]
            return super().get(request, *args, **kwargs)

        self.selected_devices = self.get_session_devices()

        if not self.selected_devices:
            messages.error(self.request, _("No devices selected for printing."))
            return redirect(self.get_success_url())

        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        return self.selected_devices

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        if self.object_list:
            institution = self.request.user.institution
            settings, _ = InstitutionSettings.objects.get_or_create(institution=institution)

            labels_data = []
            for device in self.object_list:
                labels_data.append(device.get_label_data(self.request, settings=settings))

            context['labels_data'] = labels_data
            context['header'] = settings.qr_label_header
            context['settings'] = settings

        return context

    def get_success_url(self):
        return self.request.META.get('HTTP_REFERER') or reverse_lazy('device:details')


class IssueDigitalPassportView(DeviceLogMixin, View):
    def post(self, request, *args, **kwargs):
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
        did_error = service.ensure_device_did(device)
        did_warning_message = None
        if did_error:
            error_lower = did_error.lower()
            if  "[404]" in error_lower:
                did_warning_message = "Passport issued but service endpoint not modified given that you don't own the DID."
            else:
                messages.error(request, f"Failed to issue Passport. DID configuration error: {did_error}")
                return redirect('device:details', pk=pk)

        warranty_months = request.POST.get('warranty_months', '').strip()
        raw_grade = request.POST.get('cosmetic_grade', '').strip()
        warranty_url = request.POST.get('warranty_url', '').strip()
        repair_guide = request.POST.get('repair_guide', '').strip()
        operator_notes = request.POST.get('operator_notes', '').strip()
        facility_info = self._get_facility_info(device, request)

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
            "granularityLevel": "item",
            "product": {
                "type": ["Product"],
                "id": device_uri,
                "name": f"{components.get('manufacturer', 'Unknown')} {components.get('model', 'Unknown')}",
                "description": "A personal refurbished computing device.",
                "characteristics": characteristics,
            },
            "traceabilityInformation": traceability_info
        }

        if raw_grade in CosmeticGrade.values:
            credential_subject["product"]["characteristics"]["itemCondition"] = raw_grade

        serial = components.get('serial')
        if serial and str(serial).upper() != "NA":
            credential_subject["product"]["serialNumber"] = str(serial)

        if facility_info:
            credential_subject["product"]["producedAtFacility"] = {
                "id": facility_info["id"],
                "name": facility_info["name"]
            }
            if facility_info.get("registeredId"):
                credential_subject["product"]["producedAtFacility"]["registeredId"] = str(facility_info["registeredId"])


        if repair_guide:
            credential_subject["circularityScorecard"] = {
                "type": ["CircularityPerformance"],
                "repairInformation": {
                    "type": ["Link"],
                    "linkURL": repair_guide,
                    "linkName": "Device Repair Guide"
                }
            }

        if raw_grade:
            credential_subject["product"]["characteristics"]["itemCondition"] = raw_grade

        if warranty_months or warranty_url:
            warranty_obj = {}
            if warranty_months:
                try:
                    warranty_obj["durationMonths"] = int(warranty_months)
                except ValueError:
                    pass
            if warranty_url:
                warranty_obj["termsOfService"] = warranty_url
            credential_subject["product"]["characteristics"]["warrantyPromise"] = warranty_obj

        if operator_notes:
            credential_subject["product"]["characteristics"]["operatorNotes"] = operator_notes

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
            return redirect('device:details', pk=pk)
        else:
            messages.success(request, "Digital Product Passport issued successfully!")

        dpp_url = self.request.build_absolute_uri(
            reverse('evidence:credential_detail', kwargs={'pk': credential.id})
        )
        did_error = service.ensure_device_did(device, service_endpoint=dpp_url)

        if did_error:
            error_lower = did_error.lower()
            if  "[404]" in error_lower or "[403]" in error_lower:
                messages.warning(request, "Passport issued but service endpoint not modified given that you don't own the DID.")
            else:
                messages.error(request, f"DID configuration error during endpoint update: {did_error}")

        return redirect('device:details', pk=pk)


    def _get_facility_info(self, device, request):
        facility_cred_prop = CredentialProperty.objects.filter(
            owner=device.owner,
            key='DigitalFacilityRecord'
        ).order_by('-created').first()

        if not facility_cred_prop:
            return None

        subject = facility_cred_prop.credential.get('credentialSubject', {})
        facility_data = subject.get('facility', subject)

        fac_url = self.request.build_absolute_uri(
            reverse('evidence:credential_detail', kwargs={'pk': facility_cred_prop.id})
        )

        return {
            "id": fac_url,
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
                    "linkName": f"Traceability Event - {process_name}"
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
