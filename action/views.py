from django.views import View
from django.shortcuts import redirect, get_object_or_404
from django.contrib import messages
from action.forms import ChangeStateForm, AddNoteForm
from django.views.generic.edit import DeleteView, CreateView, UpdateView, FormView
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

class UpdateNoteView(UpdateView):
    model = Note
    fields = ['description']
    template_name = "blank.html"
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

    def get_success_url(self):
        return self.request.META.get('HTTP_REFERER', reverse_lazy('device:details'))


class DeleteNoteView(View):
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
