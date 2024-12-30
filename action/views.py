from django.views import View
from django.shortcuts import redirect, get_object_or_404
from django.contrib import messages
from action.forms import ChangeStateForm, AddNoteForm
from django.views.generic.edit import DeleteView, CreateView, FormView
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from action.models import State, StateDefinition, Note, DeviceLog
from device.models import Device


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

            message = _("<Created> State '{}'. Previous State: '{}' ".format(new_state, previous_state) )
            DeviceLog.objects.create(
                snapshot_uuid=snapshot_uuid,
                event=message,
                user=self.request.user,
                institution=self.request.user.institution,
            )

            messages.success(request, _("State succesfuly changed from '{}' to '{}' ".format(previous_state, new_state) ) )
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

            message = _("<Created> Note: '{}' ".format(note) )
            DeviceLog.objects.create(
                snapshot_uuid=snapshot_uuid,
                event=message,
                user=self.request.user,
                institution=self.request.user.institution,
            )
            messages.success(request, _("Note has been added"))
        else:
            messages.error(request, "There was an error with your submission.")

        return redirect(request.META.get('HTTP_REFERER') )
