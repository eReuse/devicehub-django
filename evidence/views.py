import json

import requests
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

import json
from pyvckit.verify import verify_vc
from jsonschema import Draft202012Validator, RefResolver
from datetime import datetime



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
            is_signature_valid = verify_vc(credential_string, verify=True)
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
            if not schema_url:
                raise ValueError("Credential missing 'credentialSchema' ID.")

            schema_response = requests.get(schema_url)
            schema_response.raise_for_status()
            schema_doc = schema_response.json()

            resolver = RefResolver(base_uri=schema_url, referrer=schema_doc)
            validator = Draft202012Validator(schema_doc, resolver=resolver)

            errors = list(validator.iter_errors(credential_json))

            if not errors:
                validation_status['schema_valid'] = True
                validation_status['schema_details'] = f"Schema valid against {schema_url}."
            else:
                validation_status['schema_valid'] = False
                error_messages = [f"Error at path '{'/'.join(map(str, e.path))}'" for e in errors[:3]]
                validation_status['schema_details'] = "Schema validation failed: " + "; ".join(error_messages)

        except requests.exceptions.RequestException:
            validation_status['schema_details'] = f"Schema download failed: Could not fetch schema from {schema_url}."
        except Exception as e:
            validation_status['schema_details'] = f"Schema validation failed due to internal error: {e}"

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
