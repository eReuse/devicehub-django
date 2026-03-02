import uuid
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
from evidence.models import Evidence
from evidence.services import CredentialService

from django import forms
from utils.device import create_property, create_doc, create_index
from utils.save_snapshots import move_json, save_in_disk
from evidence.models import RootAlias

class ChangeStateView(LoginRequiredMixin, FormView):
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
            #unique id for each transformation event
            "id": f"urn:uuid:{uuid.uuid4()}",
            "eventTime": timezone.now().isoformat(),
            "eventTimeZoneOffset": "+00:00",

            "action": "observe",
            "processType": new_state,
            #TODO map specific bizstep to maybe pre-loaded states?
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

        credential, error = service.issue_device_credential(
            credential_type_key='traceability',
            credential_subject=[traceability_event],
            credential_db_key="DigitalTraceabilityEvent",
            device=device,
            uuid=snapshot_uuid,
            description=f"State Change: {previous_state} -> {new_state}"
        )

        if error:
            messages.warning(self.request, _("State changed, but credential failed: {}").format(error))
        else:
            messages.success(self.request, _("State changed and credential issued successfully from '{}' to '{}'").format(previous_state, new_state))

        return super().form_valid(form)

    def form_invalid(self, form):
        messages.error(self.request, _("There was an error with your submission."))
        return redirect(self.get_success_url())

    def get_success_url(self):
        return self.request.META.get('HTTP_REFERER') or reverse_lazy('device:details')


BULK_MATERIALS = ['Plastic', 'Aluminium', 'Copper', 'Steel', 'Glass', 'Gold', 'Lithium', 'MixedEwaste']

class DismantleDeviceView(LoginRequiredMixin, FormView):
    template_name = "dismantle_form.html"
    form_class = DeviceFormSet

    def get_success_url(self):
        return reverse('device:details', kwargs={'pk': self.kwargs['pk']})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['device'] = Device(id=self.kwargs['pk'])
        return context

    def form_valid(self, formset):
        user = self.request.user
        institution = user.institution
        parent_device_id = self.kwargs['pk']

        try:
            device = Device(id=parent_device_id, owner=institution)
            device.initial()
            parent_uuid = device.last_evidence.uuid
        except Exception as e:
            messages.error(self.request, f"Could not resolve parent device: {e}")
            return self.form_invalid(formset)

        service = CredentialService(user)
        did_error = service.ensure_device_did(device)
        if did_error:
            messages.error(self.request, f"Cannot dismantle: Parent DID configuration failed: {did_error}")
            return self.form_invalid(formset)

        parent_uri = device.did
        facility_uri = getattr(institution, 'facility_id_uri', None) or f"urn:ereuse:facility:{institution.id}"

        output_items = []
        output_quantities = []

        for form in formset:
            data = form.cleaned_data
            if not data or not data.get('type'):
                continue

            part_type = data['type']
            amount = float(data.get("amount", 1))
            part_name = data.get("name") or f"{part_type} from {parent_device_id[:6]}"

            if part_type in BULK_MATERIALS:
                output_quantities.append({
                    "type": ["QuantityElement"],
                    "quantity": amount,
                    "uom": "KGM",
                    "productId": f"urn:ereuse:class:{part_type.lower()}",
                    "productName": part_name
                })
                continue

            # Create Local Item Record
            row = {
                "type": part_type,
                "amount": 1,
                "name": part_name,
                "parent_id": parent_device_id,
                "manufactured_date": timezone.now().isoformat()
            }
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

            subpart_system_id = doc["WEB_ID"]
            subpart_uri = f"urn:ereuse:device:{subpart_system_id}"

            output_items.append({
                "type": ["Item"],
                "id": subpart_uri,
                "name": part_name
            })

        if not output_items and not output_quantities:
            messages.warning(self.request, "No valid subparts to process.")
            return self.form_invalid(formset)

        # 3. Build Transformation Payload
        event_id = f"urn:uuid:{uuid.uuid4()}"
        event_time = timezone.now().isoformat()

        ilmd_data = None
        if output_items:
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

        # Sanitize empty lists for strict schema
        cleaned_event = {k: v for k, v in transformation_event.items() if v is not None and (not isinstance(v, list) or len(v) > 0)}

        # 4. Issue Traceability Credential
        desc = f"Dismantled into {len(output_items)} components and {len(output_quantities)} material batches."

        credential, error = service.issue_device_credential(
            credential_type_key='traceability',
            credential_subject=[cleaned_event],
            credential_db_key="DigitalTraceabilityEvent",
            device=device,
            uuid=parent_uuid,
            description=desc
        )

        if error:
            messages.error(self.request, f"Dismantle failed during credential issuance: {error}")
            return self.form_invalid(formset)

        # 5. Finalize Local State
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

        messages.success(self.request, "Device dismantled successfully. Traceability Record issued.")
        return redirect('device:details', pk=parent_device_id)

class BulkStateChangeView(DashboardView, View):
    #DashboardView will redirect to a GET method
    def get(self, request, *args, **kwargs):
        state_id = self.kwargs.get('pk')
        new_state = StateDefinition.objects.filter(id=state_id).first().state
        selected_devices = self.get_session_devices()

        if not selected_devices:
            messages.error(request, _("No devices selected"))
            return self.get_success_url()
        try:
            for dev in selected_devices:

                message = _("<Created> State '{}'. Previous State: '{}'").format(new_state, dev.get_current_state().state if dev.get_current_state() else _("None") )
                State.objects.create(
                    snapshot_uuid=dev.last_uuid(),
                    state=new_state,
                    user=self.request.user,
                    institution=self.request.user.institution,
                )

                DeviceLog.objects.create(
                    snapshot_uuid=dev.last_uuid(),
                    event=message,
                    user=self.request.user,
                    institution=self.request.user.institution,
                )

            messages.success(request,_("State changed Successfully"))

        except Exception as e:
            messages.error(
                request,
                _("Error changing state on devices: %s") % str(e))

        return self.get_success_url()

    def get_success_url(self):
        return HttpResponseRedirect(self.request.META.get('HTTP_REFERER', 'dashboard:all'))


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
