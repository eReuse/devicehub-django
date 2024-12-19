from django.views import View
from django.shortcuts import redirect, get_object_or_404
from django.contrib import messages
from action.forms import ChangeStateForm, AddNoteForm
from django.views.generic.edit import DeleteView, CreateView, FormView
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from action.models import State, StateDefinition, Note
from device.models import Device
import logging


device_logger = logging.getLogger('device_log')


class ChangeStateView(View):

    def post(self, request, *args, **kwargs):
        form = ChangeStateForm(request.POST)
        
        if form.is_valid():
            previous_state = form.cleaned_data['previous_state']
            new_state = form.cleaned_data['new_state']
            snapshot_uuid = form.cleaned_data['snapshot_uuid']

            State.objects.create(
                snapshot_uuid=snapshot_uuid,
                state=new_state,
                user=self.request.user,
                institution=self.request.user.institution,
            )

            device_logger.info(f"<Updated> State to '{new_state}', from '{previous_state}' ) by user {self.request.user}.")

            message = _("State changed from '{}' to '{}'.".format(previous_state, new_state) )
            messages.success(request,message)
        else:
            messages.error(request, "There was an error with your submission.")

        return redirect(request.META.get('HTTP_REFERER') )


class UndoStateView(DeleteView):
    model = State   

    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        return super().delete(request, *args, **kwarg)

    def get_success_url(self):

        messages.info(self.request, f"Action to state: {self.object.state} has been deleted.")
        device_logger.info(f"<Deleted> State '{self.object.state}', for device '{self.object.snapshot_uuid}') by user {self.request.user}.")
        return self.request.META.get('HTTP_REFERER', reverse_lazy('device:details', args=[self.object.snapshot_uuid]))


class AddNoteView(View):

    def post(self, request, *args, **kwargs):
        form = AddNoteForm(request.POST)

        if form.is_valid():
            note = form.cleaned_data['note']
            snapshot_uuid = form.cleaned_data['snapshot_uuid']
            Note.objects.create(
                snapshot_uuid=snapshot_uuid,
                description=note,
                user=self.request.user,
                institution=self.request.user.institution,
            )
            messages.success(request, _("Note has been added"))
        else:
            messages.error(request, "There was an error with your submission.")

        return redirect(request.META.get('HTTP_REFERER') )
