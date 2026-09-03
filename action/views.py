import logging

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views.generic.edit import FormView, UpdateView

from action.forms import AddNoteForm, ChangeStateForm
from action.models import DeviceLog, Note, State, StateDefinition
from credentials.services import CredentialService
from dashboard.mixins import DashboardView
from device.models import Device


logger = logging.getLogger('django')


class ChangeStateView(LoginRequiredMixin, FormView):
    form_class = ChangeStateForm
    http_method_names = ['post']

    def form_valid(self, form):
        previous_state = form.cleaned_data['previous_state']
        new_state = form.cleaned_data['new_state']
        snapshot_uuid = form.cleaned_data['snapshot_uuid']
        self.device_id = form.cleaned_data['device_id']
        comment = form.cleaned_data.get('comment', '').strip()

        device = Device(id=self.device_id)
        logger.info(f"User {self.request.user.id} changing state for device {self.device_id}: {previous_state} -> {new_state}")

        #  check if auto-issuance is enabled
        state_def = StateDefinition.objects.filter(
            state=new_state,
            institution=self.request.user.institution
        ).first()
        auto_issue_dte = state_def.auto_issue_dte if state_def else False

        dpp_settings = self.request.user.institution.integration_settings
        is_dpp_active = dpp_settings.dpp_enabled if dpp_settings else False

        # apply local state changes and user notes
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

            if comment:
                Note.objects.create(
                    snapshot_uuid=snapshot_uuid,
                    description=comment,
                    user=self.request.user,
                    institution=self.request.user.institution,
                )
                note_log = _("<Created> Note: '{}'").format(comment)
                DeviceLog.objects.create(
                    snapshot_uuid=snapshot_uuid,
                    event=note_log,
                    user=self.request.user,
                    institution=self.request.user.institution,
                )

        # 2. Check if we should issue a Traceability Event (DTE)
        if auto_issue_dte and is_dpp_active:
            service = CredentialService(self.request.user)
            did_error = service.ensure_device_did(device)
            facility_info = service.get_facility_info(self.request)

            if did_error:
                logger.error(f"DID configuration failed for device {device.id}. Error: {did_error}")
                messages.error(self.request, _("Local state updated to '{}', but DID configuration failed. Traceability Event skipped.").format(new_state))
                return super().form_valid(form)


            default_config = state_def.dte_config if state_def and state_def.dte_config else {}
            overridden_config = dict(default_config)

            #check for dte override config
            for key, value in self.request.POST.items():
                if key.startswith('dte_cfg_'):
                    config_key = key.replace('dte_cfg_', '')
                    if value.strip():
                        overridden_config[config_key] = value.strip()
                    else:
                        overridden_config.pop(config_key, None)


            credential, error = service.issue_credential(
                workflow_type='traceability',
                build_kwargs={
                    'event_type': 'ModifyEvent',
                    'device': device,
                    'institution': self.request.user.institution,
                    'facility_info': facility_info,
                    'previous_state': previous_state,
                    'new_state': new_state,
                    'comment': comment,
                    'dte_config': overridden_config
                },
                description=f"State Change: {previous_state} -> {new_state}"
            )

            if error:
                logger.error(f"Credential issuance failed for device {self.device_id}. Error: {error}")
                messages.error(self.request, _("Local state updated to '{}', but Traceability Event issuance failed: {}").format(new_state, error))
            else:
                logger.info(f"Successfully issued traceability credential for device {self.device_id}.")
                messages.success(self.request, _("State changed to '{}' and Traceability Event issued successfully!").format(new_state))
        else:
            # state changed locally only
            messages.success(self.request, _("State changed to '{}' locally.").format(new_state))

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
            return reverse_lazy('product:details', args=[device_id])

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

        comment = request.POST.get(f'comment_{state_id}', request.POST.get('comment', '')).strip()
        posted_devices = request.POST.getlist('devices')
        if posted_devices:
            request.session['devices'] = posted_devices

        selected_devices = self.get_session_devices()

        if not selected_devices:
            messages.error(request, _("No products selected"))
            return self.get_success_url()

        logger.info(f"User {request.user.id} initiating bulk state change to '{new_state}' for {len(selected_devices)} products.")

        error_count = 0
        local_success_count = 0


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

                    if comment:
                        Note.objects.create(
                            snapshot_uuid=snapshot_uuid,
                            description=comment,
                            user=self.request.user,
                            institution=self.request.user.institution,
                        )
                        note_log = _("<Created> Note: '{}'").format(comment)
                        DeviceLog.objects.create(
                            snapshot_uuid=snapshot_uuid,
                            event=note_log,
                            user=self.request.user,
                            institution=self.request.user.institution,
                        )

                    local_success_count += 1

            except Exception as e:
                logger.exception(f"Unexpected error during bulk state update for device {dev.id}: {str(e)}")
                error_count += 1

        if local_success_count > 0:
            messages.success(request, _("State changed to '{state}' successfully for {count} devices.").format(state=new_state, count=local_success_count))
        if error_count > 0:
            messages.error(request, _("Failed to change state for {count} devices.").format(count=error_count))

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
        return self.request.META.get('HTTP_REFERER') or reverse_lazy('product:details')


class UpdateNoteView(LoginRequiredMixin, UpdateView):
    model = Note
    fields = ['description']
    pk_url_kwarg = 'pk'
    success_url = reverse_lazy('product:details')

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
        return self.request.META.get('HTTP_REFERER', reverse_lazy('product:details'))


class DeleteNoteView(LoginRequiredMixin, View):
    model = Note

    def post(self, request, *args, **kwargs):
        self.pk = kwargs['pk']
        referer = request.META.get('HTTP_REFERER', reverse('product:details'))

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
