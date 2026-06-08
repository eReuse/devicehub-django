import uuid
from django.db import transaction
from django.utils import timezone
from django.views import View
from django.urls import reverse
from django.shortcuts import redirect, get_object_or_404
from django.contrib import messages
from action.forms import ChangeStateForm, AddNoteForm
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic.edit import UpdateView, FormView
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from dashboard.mixins import DashboardView
from django.http import HttpResponseRedirect
from action.models import State, StateDefinition, Note, DeviceLog
from device.models import Device
from .models import State, DeviceLog
from device.forms import DeviceFormSet
from evidence.models import CredentialProperty
from evidence.services import CredentialService

from utils.device import create_property, create_doc, create_index
from utils.save_snapshots import move_json, save_in_disk
from evidence.models import RootAlias

class FacilityInfoMixin:
    def get_facility_info(self, institution, request):
        if not institution:
            return None

        facility_cred_prop = CredentialProperty.objects.filter(
            owner=institution,
            key='DFR'
        ).order_by('-created').first()

        if not facility_cred_prop:
            return None

        subject = facility_cred_prop.credential.get('credentialSubject', {})
        facility_data = subject.get('facility', subject)
        operated_by = facility_data.get('operatedByParty', {})

        fac_url = request.build_absolute_uri(
            reverse('evidence:credential_detail', kwargs={'uuid': facility_cred_prop.uuid})
        )

        return {
            "id": fac_url,
            "name": facility_data.get("name", "Unknown Facility"),
            "registeredId": operated_by.get("registeredId", ""),
            "idScheme": {
                "type": ["IdentifierScheme"],
                "id": "https://www.gleif.org/lei/",
                "name": "Legal Entity Identifier"
            }
        }


class ChangeStateView(LoginRequiredMixin, FacilityInfoMixin, FormView):
    form_class = ChangeStateForm

    def form_valid(self, form):
        previous_state = form.cleaned_data['previous_state']
        new_state = form.cleaned_data['new_state']
        snapshot_uuid = form.cleaned_data['snapshot_uuid']
        device_id = form.cleaned_data['device_id']
        comment = form.cleaned_data.get('comment', '').strip()
        device = Device(id=device_id)
        device.initial()

        if not device.last_evidence:
            return super().form_invalid(form)

        service = CredentialService(self.request.user)
        did_error = service.ensure_device_did(device)
        if did_error:
            messages.warning(self.request, _("State changed, but DID configuration failed"))
            return super().form_valid(form)

        components = device.components_export()
        manufacturer = components.get('manufacturer') or "Unknown"
        model = components.get('model') or "Device"
        clean_name = f"{manufacturer} {model}"

        device_uri = device.did
        inst_facility_uri = getattr(self.request.user.institution, 'facility_id_uri', None)
        facility_uri = inst_facility_uri or f"urn:uuid:{self.request.user.institution.id}"

        traceability_event = {
            "type": ["ObjectEvent", "Event"],
            "id": f"urn:uuid:{uuid.uuid4()}",
            "eventTime": timezone.now().isoformat(),
            "eventTimeZoneOffset": "+00:00",
            "action": "observe",
            "processType": new_state,
            "bizStep": "urn:epcglobal:cbv:bizstep:other",
            "disposition": "urn:epcglobal:cbv:disp:active",
            "bizLocation": facility_uri,
            "epcList": [{
                "type": ["Item"],
                "id": device_uri,
                "name": clean_name
            }],
            "ereuse:deviceState": new_state,
            "ereuse:previousState": previous_state,
            "ereuse:lastUpdate": timezone.now().isoformat()
        }

        if comment:
            traceability_event["ereuse:operatorComment"] = comment

        facility_info = self.get_facility_info(self.request.user.institution, self.request)
        if facility_info:
            traceability_event["facility"] = {
                "id": facility_info["id"],
                "name": facility_info["name"]
            }
            if facility_info.get("registeredId"):
                traceability_event["facility"]["registeredId"] = str(facility_info["registeredId"])
                traceability_event["facility"]["idScheme"] = facility_info.get("idScheme")

        try:
            with transaction.atomic():
                State.objects.create(
                    snapshot_uuid=snapshot_uuid,
                    state=new_state,
                    user=self.request.user,
                    institution=self.request.user.institution,
                )

                message = _("<Created> State '{}'. Previous State: '{}'").format(new_state, previous_state)
                DeviceLog.objects.create(
                    snapshot_uuid=snapshot_uuid,
                    event=message,
                    user=self.request.user,
                    institution=self.request.user.institution,
                )

                credential, error = service.issue_device_credential(
                    credential_type_key='traceability',
                    credential_subject=[traceability_event],
                    credential_db_key=CredentialProperty.CredentialType.DTE,
                    device=device,
                    description=f"State Change: {previous_state} -> {new_state}"
                )

                if error:
                    raise Exception(error)

            messages.success(self.request, _("State changed and credential issued successfully from '{}' to '{}'").format(previous_state, new_state))

        except Exception as e:
            messages.warning(self.request, _("State changed, but credential failed: {}").format(str(e)))

        return super().form_valid(form)

    def form_invalid(self, form):
        messages.error(self.request, _("There was an error with your submission."))
        return redirect(self.get_success_url())

    def get_success_url(self):
        return self.request.META.get('HTTP_REFERER') or reverse_lazy('device:details')

BULK_MATERIALS = ['Plastic', 'Aluminium', 'Copper', 'Steel', 'Glass', 'Gold', 'Lithium', 'MixedEwaste']

class DismantleDeviceView(LoginRequiredMixin, FacilityInfoMixin, FormView):
    template_name = "dismantle_form.html"
    form_class = DeviceFormSet

    def get_success_url(self):
        return reverse('device:details', kwargs={'pk': self.kwargs['pk']})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['device'] = Device(id=self.kwargs['pk'])
        return context

    def form_valid(self, formset):
        import json # Ensure json is imported

        user = self.request.user
        institution = user.institution
        parent_device_id = self.kwargs['pk']

        try:
            device = Device(id=parent_device_id, owner=institution)
            device.initial()
            parent_uuid = device.last_evidence.uuid
            parent_components = getattr(device, 'components', [])
        except Exception as e:
            messages.error(self.request, f"Could not resolve parent device: {e}")
            return self.form_invalid(formset)

        if isinstance(parent_components, str):
            try:
                parent_components = json.loads(parent_components)
            except json.JSONDecodeError:
                parent_components = []

        available_components = {}
        if isinstance(parent_components, list):
            for comp in parent_components:
                comp_type = comp.get('type')
                if not comp_type: continue

                if comp_type == 'RamModule' and not comp.get('size'): continue
                if comp_type == 'Storage' and not comp.get('size'): continue
                if 'no module installed' in str(comp.get('interface', '')).lower(): continue

                if comp_type not in available_components:
                    available_components[comp_type] = []
                available_components[comp_type].append(comp)

        parent_uri = getattr(device, 'did', None) or f"urn:ereuse:device:{parent_device_id}"
        facility_uri = getattr(institution, 'facility_id_uri', None) or f"urn:ereuse:facility:{institution.id}"

        output_items = []
        output_quantities = []

        for form in formset:
            data = form.cleaned_data
            if not data or not data.get('type'):
                continue

            part_type = data['type']
            amount = float(data.get("amount", 1))
            part_name = data.get("name")

            if part_type in BULK_MATERIALS:
                output_quantities.append({
                    "type": ["QuantityElement"],
                    "quantity": amount,
                    "uom": "KGM",
                    "productId": f"urn:ereuse:class:{part_type.lower()}",
                    "productName": part_name
                })
                continue

            row = {
                "type": part_type,
                "amount": 1,
            }

            if part_type in available_components and available_components[part_type]:
                real_data = available_components[part_type].pop(0)

                if not part_name:
                    mfg = real_data.get('manufacturer', '')
                    mod = real_data.get('model', '')
                    size = real_data.get('size', real_data.get('installedRam', ''))

                    smart_name = " ".join([str(p) for p in [mfg, mod, size] if p]).strip()
                    part_name = smart_name if smart_name else part_type

                for key, value in real_data.items():
                    if key.lower() not in ['type', 'name']:
                        if value:
                            row[key] = str(value)

            row["name"] = part_name or f"{part_type} from {parent_device_id[:6]}"

            if data.get("custom_id"):
                row['CUSTOM_ID'] = data["custom_id"]

            doc = create_doc(row)
            path_name = save_in_disk(doc, institution.name, place="placeholder")
            create_index(doc, user)
            create_property(doc, user, commit=True)
            move_json(path_name, institution.name, place="placeholder")

            if data.get("custom_id"):
                RootAlias.objects.create(
                    owner=institution, user=user,
                    root=f"custom_id:{data['custom_id']}",
                    alias=doc["WEB_ID"]
                )

            subpart_uri = f"urn:ereuse:device:{doc['WEB_ID']}"
            output_items.append({
                "type": ["Item"],
                "id": subpart_uri,
                "name": row["name"]
            })

        if not output_items and not output_quantities:
            messages.warning(self.request, "No valid subparts to process.")
            return self.form_invalid(formset)

        event_id = f"urn:uuid:{uuid.uuid4()}"
        event_time = timezone.now().isoformat()

        ilmd_data = None
        if output_items:
            # Instance/Lot master data (ILMD) https://ref.gs1.org/epcis/ILMD
            ilmd_data = {
                "ereuse:recoveryDate": event_time,
                "ereuse:processFacility": institution.name,
                "ereuse:parentDevice": parent_uri
            }

        transformation_event = {
            "type": ["TransformationEvent", "Event"],
            "id": event_id,
            "eventTime": event_time,
            "eventTimeZoneOffset": "+00:00",

            "processType": "Dismantling",
            "bizStep": "urn:epcglobal:cbv:bizstep:dismantling",
            "disposition": "urn:epcglobal:cbv:disp:active",

            "bizLocation": facility_uri,

            "inputEPCList": [{
                "type": ["Item"],
                "id": parent_uri,
                "name": "Parent Device"
            }],
            "outputEPCList": output_items,
            "outputQuantityList": output_quantities,
            "ilmd": ilmd_data,

            # Custom State extensions
            "ereuse:deviceState": "Dismantled",
        }

        facility_info = self.get_facility_info(institution, self.request)
        if facility_info:
            transformation_event["facility"] = {
                "id": facility_info["id"],
                "name": facility_info["name"]
            }
            if facility_info.get("registeredId"):
                transformation_event["facility"]["registeredId"] = str(facility_info["registeredId"])
                transformation_event["facility"]["idScheme"] = facility_info.get("idScheme")

        # Sanitize empty list
        cleaned_event = {k: v for k, v in transformation_event.items() if v is not None and (not isinstance(v, list) or len(v) > 0)}

        desc = f"Dismantled into {len(output_items)} components and {len(output_quantities)} material batches."

        service = CredentialService(self.request.user)
        try:
            with transaction.atomic():
                State.objects.create(
                    snapshot_uuid=parent_uuid,
                    state="Dismantled",
                    user=user,
                    institution=institution,
                )
                DeviceLog.objects.create(
                    snapshot_uuid=parent_uuid,
                    event=f"<Dismantled> {desc}",
                    user=user,
                    institution=institution,
                )

                credential, error = service.issue_device_credential(
                    credential_type_key='traceability',
                    credential_subject=[cleaned_event],
                    credential_db_key=CredentialProperty.CredentialType.DTE,
                    device=device,
                    description=desc
                )

                if error:
                    raise Exception(error)

            messages.success(self.request, "Device dismantled successfully. Traceability Record issued.")

        except Exception as e:
            messages.error(self.request, f"Dismantle failed during credential issuance: {str(e)}")
            return self.form_invalid(formset)

        return redirect('device:details', pk=parent_device_id)

class BulkStateChangeView(FacilityInfoMixin, DashboardView, View):

    def get(self, request, *args, **kwargs):
        state_id = self.kwargs.get('pk')
        state_def = StateDefinition.objects.filter(id=state_id).first()

        if not state_def:
            messages.error(request, _("Invalid state selected."))
            return self.get_success_url()

        new_state = state_def.state
        selected_devices = self.get_session_devices()

        if not selected_devices:
            messages.error(request, _("No devices selected"))
            return self.get_success_url()

        service = CredentialService(self.request.user)
        facility_info = self.get_facility_info(self.request.user.institution, self.request)

        inst_facility_uri = getattr(self.request.user.institution, 'facility_id_uri', None)
        facility_uri = inst_facility_uri or f"urn:uuid:{self.request.user.institution.id}"

        success_count = 0
        error_count = 0

        for dev in selected_devices:
            try:
                with transaction.atomic():
                    dev.initial()

                    previous_state_obj = dev.get_current_state()
                    previous_state = previous_state_obj.state if previous_state_obj else _("None")
                    snapshot_uuid = dev.last_uuid()

                    if not snapshot_uuid:
                        raise Exception("Device is missing initial evidence/snapshot.")

                    did_error = service.ensure_device_did(dev)
                    if did_error:
                        raise Exception(_("DID configuration failed."))

                    components = dev.components_export()
                    manufacturer = components.get('manufacturer') or "Unknown"
                    model = components.get('model') or "Device"
                    clean_name = f"{manufacturer} {model}"

                    traceability_event = {
                        "type": ["ObjectEvent", "Event"],
                        "id": f"urn:uuid:{uuid.uuid4()}",
                        "eventTime": timezone.now().isoformat(),
                        "eventTimeZoneOffset": "+00:00",
                        "action": "observe",
                        "processType": new_state,
                        "bizStep": "urn:epcglobal:cbv:bizstep:other",
                        "disposition": "urn:epcglobal:cbv:disp:active",
                        "bizLocation": facility_uri,
                        "epcList": [{
                            "type": ["Item"],
                            "id": dev.did,
                            "name": clean_name
                        }],
                        "ereuse:deviceState": new_state,
                        "ereuse:previousState": previous_state,
                        "ereuse:lastUpdate": timezone.now().isoformat()
                    }

                    if facility_info:
                        traceability_event["facility"] = {
                            "id": facility_info["id"],
                            "name": facility_info["name"]
                        }
                        if facility_info.get("registeredId"):
                            traceability_event["facility"]["registeredId"] = str(facility_info["registeredId"])
                            traceability_event["facility"]["idScheme"] = facility_info.get("idScheme")

                    State.objects.create(
                        snapshot_uuid=snapshot_uuid,
                        state=new_state,
                        user=self.request.user,
                        institution=self.request.user.institution,
                    )

                    message = _("<Created> State '{}'. Previous State: '{}'").format(new_state, previous_state)
                    DeviceLog.objects.create(
                        snapshot_uuid=snapshot_uuid,
                        event=message,
                        user=self.request.user,
                        institution=self.request.user.institution,
                    )

                    credential, error = service.issue_device_credential(
                        credential_type_key='traceability',
                        credential_subject=[traceability_event],
                        credential_db_key=CredentialProperty.CredentialType.DTE,
                        device=dev,
                        description=f"State Change: {previous_state} -> {new_state}"
                    )

                    if error:
                        raise Exception(error)

                    success_count += 1

            except Exception as e:
                error_count += 1

        if success_count > 0:
            messages.success(request, _("State changed and credentials issued successfully for {} devices.").format(success_count))

        if error_count > 0:
            messages.warning(request, _("Failed to process state/credentials for {} devices.").format(error_count))

        return self.get_success_url()

    def get_success_url(self):
        return HttpResponseRedirect(self.request.META.get('HTTP_REFERER', reverse_lazy('dashboard:all')))

class AddNoteView(LoginRequiredMixin, FormView):
    form_class = AddNoteForm

    def form_valid(self, form):
        note_text = form.cleaned_data['note']
        snapshot_uuid = form.cleaned_data['snapshot_uuid']
        Note.objects.create(
            snapshot_uuid=snapshot_uuid,
            description=note_text,
            user=self.request.user,
            institution=self.request.user.institution,
        )

        message = _("<Created> Note: '{}'").format(note_text)
        DeviceLog.objects.create(
            snapshot_uuid=snapshot_uuid,
            event=message,
            user=self.request.user,
            institution=self.request.user.institution,
        )
        messages.success(self.request, _("Note has been added"))
        return super().form_valid(form)

    def form_invalid(self, form):
        messages.error(self.request, _("There was an error with your submission."))
        return redirect(self.get_success_url())

    def get_success_url(self):
        return self.request.META.get('HTTP_REFERER') or reverse_lazy('device:details')


class UpdateNoteView(LoginRequiredMixin, UpdateView):
    model = Note
    fields = ['description']
    pk_url_kwarg = 'pk'

    def get_object(self, queryset=None):
        return get_object_or_404(
            Note,
            pk=self.kwargs['pk'],
            institution=self.request.user.institution,
        )

    def form_valid(self, form):
        old_description = self.get_object().description
        new_description = self.object.description
        snapshot_uuid = self.object.snapshot_uuid

        if old_description != new_description:
            message = _("<Updated> Note. Old Description: '{}'. New Description: '{}'").format(old_description, new_description)
            DeviceLog.objects.create(
                snapshot_uuid=snapshot_uuid,
                event=message,
                user=self.request.user,
                institution=self.request.user.institution,
            )
            messages.success(self.request, "Note has been updated.")
        return super().form_valid(form)

    def form_invalid(self, form):
        new_description = form.cleaned_data.get('description', '').strip()
        if not new_description:
            messages.error(self.request, _("Note cannot be empty."))
        super().form_invalid(form)
        return redirect(self.get_success_url())

    def get_success_url(self):
        return self.request.META.get('HTTP_REFERER', reverse_lazy('device:details'))


class DeleteNoteView(LoginRequiredMixin, View):
    model = Note

    def post(self, request, *args, **kwargs):
        self.pk = kwargs['pk']
        referer = request.META.get('HTTP_REFERER')
        if not referer:
            raise Http404("No referer header found")

        self.object = get_object_or_404(
            self.model,
            pk=self.pk,
            institution=self.request.user.institution
        )
        description = self.object.description
        snapshot_uuid= self.object.snapshot_uuid

        if request.user != self.object.user and not request.user.is_admin:
            messages.error(request, _("You do not have permission to delete this note."))
            return redirect(referer)

        message = _("<Deleted> Note. Description: '{}'. ").format(description)
        DeviceLog.objects.create(
            snapshot_uuid=snapshot_uuid,
            event=message,
            user=request.user,
            institution=request.user.institution,
        )
        messages.warning(self.request, _("Note '{}' deleted successfully.").format(description))

        self.object.delete()

        return redirect(referer)
