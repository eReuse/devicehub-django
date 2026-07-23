import logging
from django.db import transaction
from django.contrib import messages
from django.views import View
from django.urls import reverse, reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.shortcuts import redirect, get_object_or_404
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic.edit import UpdateView, FormView

from device.models import Device
from dashboard.mixins import DashboardView
from credentials.services import CredentialService
from action.forms import ChangeStateForm, AddNoteForm
from action.models import State, StateDefinition, Note, DeviceLog


logger = logging.getLogger('django')


class ChangeStateView(LoginRequiredMixin, FormView):
    form_class = ChangeStateForm

    # it is only a post
    http_method_names = ['post']

    def form_valid(self, form):
        previous_state = form.cleaned_data['previous_state']
        new_state = form.cleaned_data['new_state']
        snapshot_uuid = form.cleaned_data['snapshot_uuid']
        self.device_id = form.cleaned_data['device_id']
        comment = form.cleaned_data.get('comment', '').strip()

        device = Device(id=self.device_id)
        logger.info(f"User {self.request.user.id} changing state for device {self.device_id}: {previous_state} -> {new_state}")

        with transaction.atomic():
            State.objects.create(
                snapshot_uuid=snapshot_uuid,
                state=new_state,
                user=self.request.user,
                institution=self.request.user.institution,
            )

            message_log = _("<Created> State '{new}'. Previous State: '{prev}'").format(new=new_state, prev=previous_state)
            DeviceLog.objects.create(
                snapshot_uuid=snapshot_uuid,
                event=message_log,
                user=self.request.user,
                institution=self.request.user.institution,
            )

        service = CredentialService(self.request.user)
        did_error = service.ensure_device_did(device)
        facility_info = service.get_facility_info(self.request)

        if did_error:
            logger.error(f"DID configuration failed for device {device.id}. Error: {did_error}")
            messages.warning(self.request, _("Local state updated to '{}', but DID configuration failed. Credential skipped.").format(new_state))
            return super().form_valid(form)

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
            logger.error(f"Credential issuance failed for device {self.device_id}. Error: {error}")
            messages.warning(self.request, _("Local state updated to '{}', but credential issuance failed: {}").format(new_state, error))
        else:
            logger.info(f"Successfully issued traceability credential for device {self.device_id}.")
            messages.success(self.request, _("State changed to '{}' and Traceability Credential issued successfully!").format(new_state))

        return super().form_valid(form)

    def form_invalid(self, form):
        self.device_id = self.request.POST.get('device_id')
        return redirect(self.get_success_url())

    def get_success_url(self):
        referer = self.request.META.get('HTTP_REFERER')
        if referer:
            return referer

        device_id = getattr(self, 'device_id', None)
        if device_id:
            return reverse_lazy('device:details', args=[device_id])

        return reverse_lazy('dashboard:all')


class BulkStateChangeView(DashboardView, View):

    def post(self, request, *args, **kwargs):
        state_id = self.kwargs.get('pk')
        state_def = StateDefinition.objects.filter(id=state_id).first()

        referer = request.META.get('HTTP_REFERER') or reverse_lazy('dashboard:all')

        if not state_def:
            logger.warning(f"Bulk state change failed: Invalid state selected ({state_id}).")
            messages.error(request, _("Invalid state selected."))
            return redirect(referer)

        new_state = state_def.state
        selected_devices = self.get_session_devices()

        if not selected_devices:
            messages.error(request, _("No devices selected"))
            return redirect(referer)

        logger.info(f"User {request.user.id} initiating bulk state change to '{new_state}' for {len(selected_devices)} devices.")

        service = CredentialService(self.request.user)
        facility_info = service.get_facility_info(self.request)

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
                        raise ValueError(f"Device {dev.id} is missing initial evidence/snapshot.")

                    State.objects.create(
                        snapshot_uuid=snapshot_uuid,
                        state=new_state,
                        user=self.request.user,
                        institution=self.request.user.institution,
                    )

                    message = _("<Created> State '{new}'. Previous State: '{prev}'").format(new=new_state, prev=previous_state)
                    DeviceLog.objects.create(
                        snapshot_uuid=snapshot_uuid,
                        event=message,
                        user=self.request.user,
                        institution=self.request.user.institution,
                    )

                did_error = service.ensure_device_did(dev)
                if did_error:
                    logger.error(f"Bulk change DID error for device {dev.id}: {did_error}")
                    error_count += 1
                    continue

                credential, error = service.issue_credential(
                    workflow_type='traceability',
                    build_kwargs={
                        'event_type': 'ModifyEvent',
                        'device': dev,
                        'institution': self.request.user.institution,
                        'facility_info': facility_info,
                        'previous_state': previous_state,
                        'new_state': new_state,
                    },
                    description=f"Bulk State Change: {previous_state} -> {new_state}"
                )

                if error:
                    logger.error(f"Bulk change credential error for device {dev.id}: {error}")
                    error_count += 1
                else:
                    success_count += 1

            except Exception as e:
                logger.exception(f"Unexpected error during bulk state update for device {dev.id}: {str(e)}")
                error_count += 1

        if success_count > 0:
            messages.success(request, _("State changed and credentials issued successfully for {} devices.").format(success_count))
        if error_count > 0:
            messages.warning(request, _("Local state updated, but API credentials failed for {} devices.").format(error_count))

        return redirect(referer)


class AddNoteView(LoginRequiredMixin, FormView):
    form_class = AddNoteForm

    def form_valid(self, form):
        note_text = form.cleaned_data['note']
        snapshot_uuid = form.cleaned_data['snapshot_uuid']

        logger.info(f"User {self.request.user.id} adding note to snapshot {snapshot_uuid}.")

        with transaction.atomic():
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
        return super().form_invalid(form)

    def get_success_url(self):
        return self.request.META.get('HTTP_REFERER') or reverse_lazy('device:details', self.snapshot_uuid)


class UpdateNoteView(LoginRequiredMixin, UpdateView):
    model = Note
    fields = ['description']
    pk_url_kwarg = 'pk'
    success_url = reverse_lazy('device:details')

    def get_object(self, queryset=None):
        return get_object_or_404(
            Note,
            pk=self.kwargs['pk'],
            institution=self.request.user.institution,
        )

    def form_valid(self, form):
        old_description = Note.objects.get(pk=self.object.pk).description
        new_description = form.cleaned_data['description']
        snapshot_uuid = self.object.snapshot_uuid

        if old_description != new_description:
            logger.info(f"User {self.request.user.id} updating note {self.object.pk}.")
            with transaction.atomic():
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
        messages.error(self.request, _("Please correct the errors below."))
        return super().form_invalid(form)

    def get_success_url(self):
        return self.request.META.get('HTTP_REFERER', reverse_lazy('device:details'))


class DeleteNoteView(LoginRequiredMixin, View):
    model = Note

    def post(self, request, *args, **kwargs):
        self.pk = kwargs['pk']
        referer = request.META.get('HTTP_REFERER', reverse('device:details'))

        self.object = get_object_or_404(
            self.model,
            pk=self.pk,
            institution=self.request.user.institution
        )

        if request.user != self.object.user and not getattr(request.user, 'is_admin', False):
            logger.warning(f"User {request.user.id} attempted to delete note {self.pk} without permission.")
            messages.error(request, _("You do not have permission to delete this note."))
            return redirect(referer)

        description = self.object.description
        snapshot_uuid = self.object.snapshot_uuid

        logger.info(f"User {request.user.id} deleting note {self.pk}.")

        with transaction.atomic():
            message = _("<Deleted> Note. Description: '{}'. ").format(description)
            DeviceLog.objects.create(
                snapshot_uuid=snapshot_uuid,
                event=message,
                user=request.user,
                institution=request.user.institution,
            )
            self.object.delete()

        messages.success(self.request, _("Note '{}' deleted successfully.").format(description))
        return redirect(referer)
