import json

from django.contrib import messages
from urllib.parse import urlparse
from django.http import HttpResponse
from django.utils.translation import gettext_lazy as _
from django.shortcuts import get_object_or_404, redirect, Http404
from django.views.generic.base import TemplateView
from django.urls import reverse_lazy, resolve
from django.views.generic.edit import (
    DeleteView,
    FormView,
)

from action.models import DeviceLog
from dashboard.mixins import  DashboardView, Http403
from evidence.models import SystemProperty, UserProperty, Evidence
from evidence.forms import (
    UploadForm,
    UserTagForm,
    ImportForm,
    EraseServerForm
)


class ListEvidencesView(DashboardView, TemplateView):
    template_name = "evidences.html"
    section = "evidences"
    title = _("Evidences")
    breadcrumb = "Evidences"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        evidences = Evidence.get_all(self.request.user)

        context.update({
            'evidences': evidences,
        })
        return context


class UploadView(DashboardView, FormView):
    template_name = "upload.html"
    section = "evidences"
    title = _("Upload Evidence")
    breadcrumb = "Evidences / Upload"
    success_url = reverse_lazy('evidence:list')
    form_class = UploadForm

    def form_valid(self, form):
        form.save(self.request.user)
        messages.success(self.request, _("Evidence uploaded successfully."))
        response = super().form_valid(form)
        return response

    def form_invalid(self, form):
        response = super().form_invalid(form)
        return response


class ImportView(DashboardView, FormView):
    template_name = "upload.html"
    section = "evidences"
    title = _("Import Evidence")
    breadcrumb = "Evidences / Import"
    success_url = reverse_lazy('evidence:list')
    form_class = ImportForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def form_valid(self, form):
        form.save()
        messages.success(self.request, _("Evidence imported successfully."))
        response = super().form_valid(form)
        return response

    def form_invalid(self, form):
        response = super().form_invalid(form)
        return response


class EvidenceView(DashboardView, FormView):
    template_name = "ev_details.html"
    section = "evidences"
    title = _("Evidences")
    breadcrumb = "Evidences / Details"
    success_url = reverse_lazy('evidence:list')
    form_class = UserTagForm

    def get(self, request, *args, **kwargs):
        self.pk = kwargs['pk']
        self.object = Evidence(self.pk)
        if self.object.owner != self.request.user.institution:
            raise Http403

        self.object.get_properties()
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'object': self.object,
            'form2': EraseServerForm(**self.get_form_kwargs(), data=self.request.POST or None),
        })
        return context

    def get_form_kwargs(self):
        self.pk = self.kwargs.get('pk')
        kwargs = super().get_form_kwargs()
        kwargs['uuid'] = self.pk
        kwargs['user'] = self.request.user
        return kwargs

    def post(self, request, *args, **kwargs):
        form1 = self.get_form()
        #Empty param @initial makes it work, but i doubt it is the correct logic
        form2 = EraseServerForm(request.POST, user=self.request.user, initial={}, uuid=self.kwargs.get('pk'))

        if "submit_form1" in request.POST and form1.is_valid():
            return self.form_valid(form1)
        elif "submit_form2" in request.POST and form2.is_valid():
            return self.form2_valid(form2)

        return self.form_invalid(form1, form2)

    def form2_valid(self, form):
        form.save(self.request.user)
        response = super().form_valid(form)
        return response

    def form_valid(self, form):
        form.save(self.request.user)
        response = super().form_valid(form)
        return response

    def form_invalid(self, form):
        response = super().form_invalid(form)
        return response

    def get_success_url(self):
        success_url = reverse_lazy('evidence:details', args=[self.pk])
        return success_url


class DownloadEvidenceView(DashboardView, TemplateView):

    def get(self, request, *args, **kwargs):
        pk = kwargs['pk']
        evidence = Evidence(pk)
        if evidence.owner != self.request.user.institution:
            raise Http403()

        evidence.get_doc()
        data = json.dumps(evidence.doc)
        response = HttpResponse(data, content_type="application/json")
        response['Content-Disposition'] = 'attachment; filename={}'.format("evidence.json")
        return response


class DeleteEvidenceTagView(DashboardView, DeleteView):
    model = SystemProperty

    def get_queryset(self):
        # only those with 'CUSTOM_ID'
        return SystemProperty.objects.filter(owner=self.request.user.institution, key='CUSTOM_ID')

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()

        message = _("<Deleted> Evidence Tag: {}").format(self.object.value)
        DeviceLog.objects.create(
            snapshot_uuid=self.object.uuid,
            event=message,
            user=self.request.user,
            institution=self.request.user.institution
        )
        self.object.delete()

        messages.info(self.request, _("Evicende Tag deleted successfully."))
        return self.handle_success()

    def handle_success(self):
        return redirect(self.get_success_url())

    def get_success_url(self):
        return self.request.META.get(
            'HTTP_REFERER',
            reverse_lazy('evidence:details', args=[self.object.uuid])
        )
