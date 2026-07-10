import uuid
import datetime
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
from django.http import HttpResponseRedirect, Http404
from action.models import State, StateDefinition, Note, DeviceLog
from device.models import Device
from .models import State, DeviceLog
from device.forms import DeviceFormSet
from evidence.models import CredentialProperty
from credentials.services import CredentialService

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

        with transaction.atomic():
            State.objects.create(
                snapshot_uuid=snapshot_uuid,
                state=new_state,
                user=self.request.user,
                institution=self.request.user.institution,
            )

            message_log = _("<Created> State '{}'. Previous State: '{}'").format(new_state, previous_state)
            DeviceLog.objects.create(
                snapshot_uuid=snapshot_uuid,
                event=message_log,
                user=self.request.user,
                institution=self.request.user.institution,
            )

        service = CredentialService(self.request.user)
        did_error = service.ensure_device_did(device)

        if did_error:
            messages.warning(self.request, _("Local state updated to '{}', but DID configuration failed. Credential skipped.").format(new_state))
            return super().form_valid(form)

        facility_info = self.get_facility_info(self.request.user.institution, self.request)

        credential, error = service.issue_credential(
            workflow_type='traceability',
            build_kwargs={
                'event_type': 'ModifyEvent',
                'device': device,
                'institution': self.request.user.institution,
                'facility_info': facility_info,
                'previous_state': previous_state,
                'new_state': new_state,
                'comment': comment
            },
            description=f"State Change: {previous_state} -> {new_state}"
        )

        if error:
            messages.warning(self.request, _("Local state updated to '{}', but credential issuance failed: {}").format(new_state, error))
        else:
            messages.success(self.request, _("State changed to '{}' and Traceability Credential issued successfully!").format(new_state))

        return super().form_valid(form)

    def form_invalid(self, form):
        messages.error(self.request, _("There was an error with your submission."))
        return redirect(self.get_success_url())

    def get_success_url(self):
        return self.request.META.get('HTTP_REFERER') or reverse_lazy('device:details')


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
