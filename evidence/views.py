import json
import os

from django.contrib import messages
from django.http import HttpResponse, FileResponse
from django.utils.translation import gettext_lazy as _
from django.shortcuts import get_object_or_404, redirect, Http404
from django.views.generic.base import TemplateView
from django.urls import reverse_lazy
from django.views.generic.edit import (
    DeleteView,
    FormView,
)

from action.models import DeviceLog
from dashboard.mixins import  DashboardView, Http403
from evidence.models import SystemProperty, RootAlias, Evidence
from evidence.forms import (
    UploadForm,
    UserAliasForm,
    ImportForm,
    EraseServerForm,
    PhotoForm
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


class ImportPhotoView(DashboardView, FormView):
    template_name = "upload.html"
    section = "evidences"
    title = _("Import Photo Evidence")
    breadcrumb = "Evidences / Photo"
    success_url = reverse_lazy('evidence:list')
    form_class = PhotoForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def form_valid(self, form):
        form.save()
        messages.success(self.request, _("Photo evidence uploaded successfully."))
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
    form_class = UserAliasForm

    def get_object(self):
        self.pk = self.kwargs['pk']
        self.object = Evidence(self.pk)
        if self.object.owner != self.request.user.institution:
            raise Http403

    def get(self, request, *args, **kwargs):
        self.get_object()
        self.object.get_properties()
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'object': self.object,
            'form2': EraseServerForm(**self.get_form_erase_kwargs()),
        })
        return context

    def get_form_erase_kwargs(self):
        self.pk = self.kwargs.get('pk')
        kwargs = super().get_form_kwargs()
        kwargs['uuid'] = self.pk
        kwargs['user'] = self.request.user
        return kwargs

    def get_form_kwargs(self):
        self.pk = self.kwargs.get('pk')
        kwargs = super().get_form_kwargs()
        instance = get_object_or_404(
            SystemProperty,
            uuid=self.pk,
            owner=self.request.user.institution
        )
        kwargs['uuid'] = self.pk
        kwargs['instance'] = instance
        kwargs['user'] = self.request.user
        return kwargs

    def form_valid(self, form):
        form.save()
        response = super().form_valid(form)
        return response

    def form_invalid(self, form):
        for field, errors in form.errors.items():
            for error in errors:
                if field == '__all__':
                    messages.error(self.request, error)
                else:
                    messages.error(self.request, f"{field.title()}: {error}")

        self.get_object()
        return super().form_invalid(form)

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


class PhotoEvidenceView(DashboardView, TemplateView):
    """View to serve photo evidence files"""

    def get(self, request, *args, **kwargs):
        from utils.photo_evidence import get_photos_dir

        pk = kwargs['pk']
        evidence = Evidence(pk)
        if evidence.owner != self.request.user.institution:
            raise Http403()

        evidence.get_doc()

        # Check if this is actually a photo evidence
        if not evidence.is_photo_evidence():
            raise Http404("This evidence is not a photo")

        # Get photo data from document
        photo_data = evidence.doc.get('photo')
        if not photo_data:
            raise Http404("Photo data not found")

        # Construct file path
        photo_filename = photo_data.get('name')
        if not photo_filename:
            raise Http404("Photo filename not found")

        photos_dir = get_photos_dir(evidence.owner.name)
        file_path = os.path.join(photos_dir, photo_filename)

        if not os.path.exists(file_path):
            raise Http404("Photo file not found on disk")

        # Serve the file
        response = FileResponse(open(file_path, 'rb'), content_type=photo_data.get('mime_type', 'image/jpeg'))
        return response


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


class DeleteEvidenceAliasView(DashboardView, DeleteView):
    model = SystemProperty

    def get_queryset(self):
        return RootAlias.objects.filter(owner=self.request.user.institution)

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        self.snapshot_id = kwargs.get("snapshot_id")

        message = _("<Deleted> Evidence alias: {}").format(self.object.root)
        DeviceLog.objects.create(
            snapshot_uuid=self.snapshot_id,
            event=message,
            user=self.request.user,
            institution=self.request.user.institution
        )
        self.object.delete()

        messages.info(self.request, _("Evicende alias deleted successfully."))
        return self.handle_success()

    def handle_success(self):
        return redirect(self.get_success_url())

    def get_success_url(self):
        return self.request.META.get(
            'HTTP_REFERER',
            reverse_lazy('evidence:details', args=[self.snapshot_id])
        )
