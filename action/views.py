from django.views import View
from django.shortcuts import redirect, get_object_or_404
from django.contrib import messages
from action.forms import ChangeStateForm, AddNoteForm
from django.views.generic.edit import DeleteView, CreateView, UpdateView, FormView
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from action.models import State, StateDefinition, Note, DeviceLog
from device.models import Device


class ChangeStateView(FormView):
    form_class = ChangeStateForm

    def form_valid(self, form):
        previous_state = form.cleaned_data['previous_state']
        new_state = form.cleaned_data['new_state']
        snapshot_uuid = form.cleaned_data['snapshot_uuid']

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
        messages.success(self.request, _("State successfully changed from '{}' to '{}'").format(previous_state, new_state))
        return super().form_valid(form)

    def form_invalid(self, form):
        messages.error(self.request, _("There was an error with your submission."))
        return redirect(self.get_success_url())

    def get_success_url(self):
        return self.request.META.get('HTTP_REFERER') or reverse_lazy('device:details')


class AddNoteView(FormView):
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


class UpdateNoteView(UpdateView):
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
