import json
import os

from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.utils.translation import gettext_lazy as _
from django.shortcuts import get_object_or_404, redirect, Http404
from django.views.generic.base import TemplateView
from django.views.generic import DetailView
from django.urls import reverse_lazy
from django.views.generic.edit import (
    DeleteView,
    FormView,
)

from action.models import DeviceLog
from dashboard.mixins import  DashboardView, Http403
from evidence.models import SystemProperty, CredentialProperty, Evidence
from evidence.forms import (
    UploadForm,
    UserAliasForm,
    ImportForm,
    EraseServerForm,
    PhotoForm
)
from django_tables2 import SingleTableView
from evidence.tables import EvidenceTable

from pyvckit.verify import verify_signature, verify_schema


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


class CredentialDetailView(DetailView):
    model = CredentialProperty
    context_object_name = 'credential_prop'

    def render_to_response(self, context, **response_kwargs):
        """
        Overridden to handle ?format=json for direct downloads.
        """
        if self.request.GET.get('format') == 'json':
            credential_data = self.object.credential or {}

            cred_id = credential_data.get('id', '').split(':')[-1]
            filename = f"credential_{cred_id or self.object.pk}.json"

            response = JsonResponse(credential_data, json_dumps_params={'indent': 2})
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            return response

        # Otherwise, render the HTML template as normal
        return super().render_to_response(context, **response_kwargs)

    def get_template_names(self):
        obj = self.get_object()
        credential = obj.credential or {}

        subject = credential.get('credentialSubject', {})
        types = credential.get('type', [])

        if isinstance(subject, list):
            return ["traceability_credential.html"]

        if 'facility' in subject or 'DigitalFacilityRecord' in types:
            return ["facility_credential.html"]

        if 'product' in subject or 'DigitalProductPassport' in types:
            return ["dpp_credential.html"]

        return ["credential_base.html"]

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


class ValidateDPPView(TemplateView):
    def get(self, request, pk, *args, **kwargs):
        try:
            credential_prop = get_object_or_404(CredentialProperty, pk=pk)
            credential_data = credential_prop.credential
        except Http404:
            messages.error(request, _("Error: Credential with ID {pk} not found in the database.").format(pk=pk))
            return redirect(reverse_lazy('evidence:credential_detail', kwargs={'pk': pk}))

        results = self.perform_full_dpp_validation(credential_data)

        validation_status = results['status']
        crypto_details = results['validation_results']['cryptographic_details']
        schema_details = results['validation_results']['schema_details']

        if validation_status == 'verified':
            full_message = _("DPP Validation Successful! Cryptography and Schema checks passed.")
            messages.success(request, full_message)
        else:
            full_message = _(
                "DPP Validation Failed. "
                "Cryptography Status: {crypto_status}. "
                "Schema Status: {schema_status}."
            ).format(
                crypto_status=crypto_details,
                schema_status=schema_details
            )
            messages.error(request, full_message)

        return redirect(reverse_lazy('evidence:credential_detail', kwargs={'pk': pk}))


    def perform_full_dpp_validation(self, credential_json: dict) -> dict:

        validation_status = {
            'cryptographic_valid': False,
            'cryptographic_details': 'Verification pending...',
            'schema_valid': False,
            'schema_details': 'Verification pending...'
        }

        credential_string = json.dumps(credential_json)

        try:
            is_signature_valid = verify_signature(credential_string, verify=True)
            validation_status['cryptographic_valid'] = is_signature_valid

            if is_signature_valid:
                validation_status['cryptographic_details'] = 'Signature successfully verified and identity confirmed.'
            else:
                validation_status['cryptographic_details'] = 'Signature verification failed (data tampered or key invalid).'

        except Exception as e:
            validation_status['cryptographic_details'] = f"Cryptographic verification error: {e.__class__.__name__}: {e}"
            validation_status['cryptographic_valid'] = False


        try:
            schema_url = credential_json.get('credentialSchema', {}).get('id')
            is_signature_valid = verify_schema(credential_string, verify=True)
            validation_status['schema_valid'] = True

            validation_status['schema_details'] = f"Schema valid against {schema_url}."

        except requests.exceptions.RequestException:
            validation_status['schema_valid'] = False
            validation_status['schema_details'] = f"Schema download failed: Could not fetch schema from {schema_url}."
        except Exception as e:
            validation_status['schema_valid'] = False
            validation_status['schema_details'] = f"Schema validation failed: {e}"

        final_status = 'verified' if validation_status['cryptographic_valid'] and validation_status['schema_valid'] else 'failed'

        return {
            'status': final_status,
            'validation_results': validation_status
        }

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
