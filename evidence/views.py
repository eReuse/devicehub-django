from django.utils.translation import gettext_lazy as _
from django.views.generic.base import TemplateView
from django.urls import reverse_lazy
from django.views.generic.edit import (
    FormView,
)

from dashboard.mixins import  DashboardView
from evidence.models import Evidence
from evidence.forms import UploadForm
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
