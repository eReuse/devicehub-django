from django.views import View
from django.shortcuts import redirect, get_object_or_404
from django.contrib import messages
from action.forms import AddStateForm
from django.views.generic.edit import DeleteView
from django.urls import reverse_lazy
from action.models import State, StateDefinition
from device.models import Device
import logging


device_logger = logging.getLogger('device_log')

class NewActionView(View):

    def post(self, request, *args, **kwargs):
        form = AddStateForm(request.POST)
        
        if form.is_valid():
            state_definition_id = form.cleaned_data['state_id']
            state_definition = get_object_or_404(StateDefinition, pk=state_definition_id)
            snapshot_uuid = form.cleaned_data['snapshot_uuid']
            #TODO: implement notes
            note = form.cleaned_data.get('note', '')

            state = State.objects.create(
                snapshot_uuid=snapshot_uuid,
                state=state_definition.state,
                user=request.user,
                institution=request.user.institution,
            )
            #TODO: also change logger for full fledged table
            device_logger.info(
            f"Updated State to (key='{state_definition.state}', for device value='{snapshot_uuid}') by user {self.request.user}."
        )

            messages.success(request, f"Action to '{state_definition.state}' has been added.")
            return redirect(request.META.get('HTTP_REFERER'))
        else:
            messages.error(request, "There was an error with your submission.")
            return redirect(request.META.get('HTTP_REFERER'))

class ActionUndoView(DeleteView):
    model = State
    success_url = reverse_lazy('state_list')

    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        time_since_creation = timezone.now() - self.object.date
        if time_since_creation.total_seconds() <= 3600:  # 1 hour is 3600 seconds
            return super().delete(request, *args, **kwargs)
        else:
            messages.error(request, "You can undo an action within one hour of its creation.")
            return redirect(request.META.get('HTTP_REFERER'))
