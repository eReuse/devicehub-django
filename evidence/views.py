import json

from django.contrib import messages
from urllib.parse import urlparse
from django.http import HttpResponse
from django.utils.translation import gettext_lazy as _
from django.shortcuts import get_object_or_404, redirect, Http404
from django.views.generic.base import TemplateView
from django.urls import reverse_lazy, resolve
from django.views.generic import DetailView
from django.views.generic.edit import (
    DeleteView,
    FormView,
)

from action.models import DeviceLog
from dashboard.mixins import  DashboardView, Http403
from evidence.models import SystemProperty, CredentialProperty, Evidence
from evidence.forms import (
    UploadForm,
    UserTagForm,
    ImportForm,
    EraseServerForm
)
from django_tables2 import SingleTableView
from evidence.tables import EvidenceTable


class ListEvidencesView(DashboardView, SingleTableView):
    template_name = "evidences.html"
    section = "evidences"
    table_class = EvidenceTable
    title = _("Evidences")
    breadcrumb = "Evidences"
    paginate_by = 13

    def get_queryset(self):
        return Evidence.get_all(self.request.user)


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

class CredentialDetailView(DetailView):

    model = CredentialProperty
    template_name = 'credential_details.html'
    context_object_name = 'credential_prop'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['credential'] = self.object.credential
        return context

class DownloadDPPView(DashboardView, TemplateView):
    def get(self, request, *args, **kwargs):
        pk = kwargs.get('pk')
        try:
            credential_prop = get_object_or_404(CredentialProperty, pk=pk)

            data = json.dumps(credential_prop.credential, indent=4)
            response = HttpResponse(data, content_type="application/json")
            response['Content-Disposition'] = f'attachment; filename="dpp_credential_{pk}.json"'
            return response
        except CredentialProperty.DoesNotExist:
            raise Http404("Credential not found.")


class CredentialByEvidenceUUIDView(TemplateView):
    def get(self, request, *args, **kwargs):
        uuid = kwargs.get('uuid')
        credential_prop = CredentialProperty.objects.filter(uuid=uuid).order_by('-created').first()

        if credential_prop:
            return redirect('evidence:credential_detail', pk=credential_prop.pk)
        else:
            raise Http404("No credential found for the specified evidence UUID.")


class EraseServerView(DashboardView, FormView):
    template_name = "ev_details.html"
    section = "evidences"
    title = _("Evidences")
    breadcrumb = "Evidences / Details"
    success_url = reverse_lazy('evidence:list')
    form_class = EraseServerForm

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
        })
        return context

    def get_form_kwargs(self):
        self.pk = self.kwargs.get('pk')
        kwargs = super().get_form_kwargs()
        kwargs['uuid'] = self.pk
        kwargs['user'] = self.request.user
        return kwargs

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
