import json

from django.http import HttpResponse
from django.utils.translation import gettext_lazy as _
from django.views.generic.base import TemplateView
from django.urls import reverse_lazy
from django.views.generic.edit import (
    FormView,
)

from dashboard.mixins import  DashboardView, Http403
from evidence.models import Evidence
from evidence.forms import UploadForm, UserTagForm
# from django.shortcuts import render
# from rest_framework import viewsets
# from snapshot.serializers import SnapshotSerializer


# class SnapshotViewSet(viewsets.ModelViewSet):
#     queryset = Snapshot.objects.all()
#     serializer_class = SnapshotSerializer


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
        if self.object.owner != self.request.user:
            raise Http403

        self.object.get_annotations()
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
        if evidence.owner != self.request.user:
            raise Http403()

        evidence.get_doc()
        data = json.dumps(evidence.doc)
        response = HttpResponse(data, content_type="application/json")
        response['Content-Disposition'] = 'attachment; filename={}'.format("credential.json")
        return response
