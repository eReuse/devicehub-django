import logging

from django.db.models import Q
from collections import defaultdict
from django.http import JsonResponse
from django.conf import settings
from django.db import IntegrityError, models
from django.urls import reverse_lazy, resolve
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, Http404, render
from django.db import transaction
from django.http import HttpResponseForbidden
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
from evidence.models import UserProperty, SystemProperty, Evidence, RootAlias, CredentialProperty
from lot.models import LotTag
from device.models import Device
from device.forms import DeviceAttributeFormSet, DeviceMainForm, DEVICE_ATTRIBUTE_SUGGESTIONS
from device.forms import DeviceFormSet
from evidence.tables import EvidenceTable, CredentialTable
from django_tables2 import RequestConfig
from user.models import InstitutionLabelSettings
from credentials.services import CredentialService
if settings.DPP:
    from dpp.models import Proof
    from dpp.api_dlt import PROOF_TYPE


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
            sysprop__in=self.object.properties,
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
            settings, _ = InstitutionLabelSettings.objects.get_or_create(institution=institution)

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
        device = Device(id=pk, owner=request.user.institution)

        if not device.last_evidence:
            messages.error(request, "Device not found.")
            return redirect('device:list')

        device.initial()
        service = CredentialService(request.user)

        # ensure device has a did assigned
        did_error = service.ensure_device_did(device)
        did_warning_message = None

        if did_error:
            if "[404]" in did_error.lower():
                did_warning_message = "Passport issued but service endpoint not modified given that you don't own the DID."
            else:
                messages.error(request, f"Failed to issue Passport. DID configuration error: {did_error}")
                return redirect('device:details', pk=pk)

        # gather databaase information for the dpp builder
        facility_info = self._get_facility_info(device, self.request)
        traceability_info = self._get_traceability_info(device, self.request)
        components = device.components_export() or {}
        device_name = components.get('model', 'Unknown Device')

        credential, error = service.issue_credential(
            workflow_type='dpp',
            build_kwargs={
                'device': device,
                'institution': request.user.institution,
                'post_data': request.POST,
                'facility_info': facility_info,
                'traceability_info': traceability_info
            },
            description=f"Digital Product Passport - {device_name}"
        )

        if error:
            messages.error(request, f"Failed to issue Passport: {error}")
            return redirect('device:details', pk=pk)

        messages.success(request, "Digital Product Passport issued successfully!")

        # add the devices dpp view to the did servicenedpoint
        dpp_url = request.build_absolute_uri(
            reverse('evidence:credential_detail', kwargs={'uuid': credential.uuid})
        )
        did_update_error = service.ensure_device_did(device, service_endpoint=dpp_url)

        if did_update_error:
            if "[404]" in did_update_error.lower() or "[403]" in did_update_error.lower():
                messages.warning(request, did_warning_message or "Passport issued but service endpoint not modified given that you don't own the DID.")
            else:
                messages.error(request, f"DID configuration error during endpoint update: {did_update_error}")
        elif did_warning_message:
            messages.warning(request, did_warning_message)

        return redirect('device:details', pk=pk)


    def _get_facility_info(self, device, request):
        institution = device.owner
        if not institution or not institution.latest_facility_credential:
            return None

        facility_cred_prop = institution.latest_facility_credential
        subject = facility_cred_prop.credential.get('credentialSubject', {})
        facility_data = subject.get('facility', subject)
        operated_by = facility_data.get('operatedByParty', {})

        return {
            "id": request.build_absolute_uri(reverse('evidence:credential_detail', kwargs={'uuid': facility_cred_prop.uuid})),
            "name": facility_data.get("name", "Unknown Facility"),
            "registeredId": operated_by.get("registeredId", ""),
            "idScheme": {
                "type": ["IdentifierScheme"],
                "id": "https://www.gleif.org/lei/",
                "name": "Legal Entity Identifier"
            }
        }

    def _get_traceability_info(self, device, request):
        events = CredentialProperty.objects.filter(
            sysprop__uuid__in=device.uuids, key='DTE'
        ).order_by('created')

        if not events: return []

        grouped = defaultdict(list)
        for prop in events:
            subject = prop.credential.get('credentialSubject', [])
            if isinstance(subject, dict):
                subject = [subject]

            for event in subject:
                raw_process = event.get('processType', 'Unknown')
                process_name = raw_process.split(':')[-1].capitalize() if ':' in raw_process else raw_process
                cred_url = request.build_absolute_uri(reverse('evidence:credential_detail', kwargs={'uuid': prop.uuid}))

                grouped[process_name].append({
                    "type": ["SecureLink", "Link"],
                    "linkURL": cred_url,
                    "linkName": f"Traceability Event - {process_name}"
                })

        return [
            {
                "type": ["TraceabilityPerformance"],
                "valueChainProcess": process,
                "verifiedRatio": 1.0,
                "traceabilityEvent": links
            }
            for process, links in grouped.items()
        ]

class DeviceDPPView(TemplateView):
    template_name = "dpp_credential.html"

    def get(self, request, *args, **kwargs):
        self.pk = kwargs.get('pk')

        root = RootAlias.objects.filter(alias=self.pk).first()
        if root:
            return redirect(request.resolver_match.view_name, pk=root.root)

        try:
            self.device = Device(id=self.pk)
            self.device.initial()
        except Exception:
            raise Http404(_("Device not found."))

        if not self.device.last_evidence:
            raise Http404(_("No evidence found for this device."))

        self.latest_dpp_cred = CredentialProperty.objects.filter(
            sysprop__in=self.device.properties,
            key=CredentialProperty.CredentialType.DPP
        ).order_by('-created').first()

        if not self.latest_dpp_cred:
            messages.info(request, _("A Digital Product Passport (DPP) has not been generated for this device yet."))
            return redirect(reverse_lazy('device:details', args=[self.pk]))

        # Handle JSON download early return
        if request.GET.get('format') == 'json':
            return self._serve_json_download()

        return super().get(request, *args, **kwargs)

    def _serve_json_download(self):
        """Helper to encapsulate the JSON download response."""
        credential_data = self.latest_dpp_cred.credential or {}
        cred_id = credential_data.get('id', '').split(':')[-1]
        filename = f"credential_{cred_id or self.device.id}.json"

        response = JsonResponse(credential_data, json_dumps_params={'indent': 2})
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.latest_dpp_cred:
            context['credential'] = self.latest_dpp_cred.credential

        return context
