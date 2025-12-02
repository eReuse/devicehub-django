import logging

from django.contrib import messages
from django.db import IntegrityError
from django.urls import reverse_lazy
from django.http import HttpResponse
from django.views.generic.edit import FormView
from django.shortcuts import get_object_or_404, Http404, redirect, render
from django.utils.translation import gettext_lazy as _
from django_tables2 import SingleTableView
from django.views.generic.base import TemplateView
from django.views.generic.edit import (
    CreateView,
)

from environmental_impact.algorithms.algorithm_factory import FactoryEnvironmentImpactAlgorithm as Feia
from dashboard.mixins import DashboardView
from action.models import StateDefinition, State, DeviceLog, Note
from device.views import DeviceLogMixin, DeleteUserPropertyView, UpdateUserPropertyView
from lot.models import Lot, LotTag
from device.models import Device
from evidence.models import Evidence, UserProperty, SystemProperty
from transfer.models import Transfer
from transfer.forms import TransferForm
from transfer.tables import TransferTable, DeviceTable


logger = logging.getLogger(__name__)


class TransferTagMixing(DashboardView, SingleTableView):
    template_name = "transfers.html"
    title = _("Transfers")
    breadcrumb = _("transfers") + " / "
    success_url = reverse_lazy('dashboard:unassigned')
    model = Transfer
    table_class = TransferTable
    paginate_by = 10

    def get_queryset(self):
        return self.model.objects.filter(owner=self.request.user.institution)

    def get_context_data(self, **kwargs):
        self.get_queryset()
        context = super().get_context_data(**kwargs)
        context.update({
            'title': self.title,
            'breadcrumb': self.breadcrumb,
            'search_query': "",
        })
        return context

class TransferSendedView(TransferTagMixing):
    breadcrumb = _("transfers") + " / " + _("sended")

    def get_queryset(self):
        return self.model.objects.filter(
            owner=self.request.user.institution,
            type=self.model.Type.SENDED
        )


class TransferReceivedView(TransferTagMixing):
    breadcrumb = _("transfers") + " / " + _("received")

    def get_queryset(self):
        return self.model.objects.filter(
            owner=self.request.user.institution,
            type=self.model.Type.RECEIVED
        )


class TransferView(DashboardView, SingleTableView):
    template_name = "transfers.html"
    title = _("Transfer")
    breadcrumb = _("transfer") + " / " + _("lot")
    model = Transfer
    table_class = DeviceTable
    paginate_by = 10

    def get(self, request, *args, **kwargs):
        self.object = get_object_or_404(
            self.model,
            owner=self.request.user.institution,
            id=self.kwargs.get("id")
        )

        if self.kwargs.get("reference") and self.object.reference:
           ref_object = self.model.objects.filter(
               owner=self.request.user.institution,
               credential_id=self.object.reference
           ).first()
           if ref_object:
               return redirect(reverse_lazy('transfer:id', args=[ref_object.id]))
           else:
               return redirect(self.object.reference)

        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        items = []
        for i in self.object.get_items():
            try:
                i["id"] = i["id"].split("/")[-3]
            except Exception:
                pass

            items.append(i)
        return items

    def get_context_data(self, **kwargs):
        self.get_queryset()
        context = super().get_context_data(**kwargs)
        context.update({
            'title': self.title,
            'breadcrumb': self.breadcrumb,
            'search_query': "",
            'path': 'tag',
            'lot': self.object.lot_set.first(),
            'transfer': self.object,
        })
        return context


class NewTransferView(DashboardView, FormView):
    template_name = "transfer_lots.html"
    title = _("Transfer lot/s")
    breadcrumb = "transfer / new"
    success_url = reverse_lazy('dashboard:unassigned')
    form_class = TransferForm

    def get(self, request, *args, **kwargs):
        response =  super().get(request, *args, **kwargs)
        ids = self.lot.devices.values("device_id")
        if not ids:
            messages.error(self.request, _("No there are devices in this lot"))
            return redirect(reverse_lazy('dashboard:lot', args=[self.lot.id]))

        transfers = SystemProperty.objects.filter(
            value__in=ids,
            owner=self.request.user.institution,
            transfer__type=Transfer.Type.SENDED
        ).first()

        if transfers:
            messages.error(self.request, _("There are devices sended in this lot"))
            return redirect(reverse_lazy('dashboard:lot', args=[self.lot.id]))

        return response

    def get_success_url(self):
        return reverse_lazy('transfer:id', args=[self.transfer.id])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'lot': self.lot,
            'lots_with_devices': self.lot.devices.exists(),
            'breadcrumb': self.breadcrumb,
            'title': self.title,
        })

        return context

    def get_form_kwargs(self):
        self.lot = get_object_or_404(
            Lot,
            owner=self.request.user.institution,
            id=self.kwargs.get("lot_id"),
            transfer=None
        )
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        kwargs['domain'] = "{}://{}".format(self.request.scheme, self.request.get_host())
        kwargs['lot'] = self.lot
        return kwargs

    def form_valid(self, form):
        form.save()

        if form.instance:
            messages.success(self.request, _("Lot succesfully transfer"))
            self.transfer = form.instance
        else:
            messages.error(self.request, _("Error signing transaction"))

        response = super().form_valid(form)
        return response

    def form_invalid(self, form):
        messages.error(self.request, _("Lot error transfer"))
        response = super().form_invalid(form)
        return response


class SendTransferView(DashboardView, TemplateView):
    object = None

    def get(self, request, *args, **kwargs):
        super().get(request, *args, **kwargs)
        self.request = request
        self.args = args
        self.kwargs = kwargs
        self.get_object()
        try:
            self.object.send_transfer()
        except Exception as err:
            logger.error("Sending Transfer: {}".format(err))
            messages.error(self.request, _("Error sending transfer"))
            return redirect(self.get_success_url())

        messages.success(self.request, _("Transfer succesfully sended"))
        return redirect(self.get_success_url())

    def get_object(self):
        if self.object:
            return self.object

        self.object = get_object_or_404(
            Transfer,
            owner=self.request.user.institution,
            id=self.kwargs.get("id"),
            sended=False
        )

    def get_success_url(self):
        return reverse_lazy('transfer:id', args=[self.object.id])


class EditTransferView(DashboardView, FormView):
    template_name = "transfer_lots.html"
    title = _("Transfer lot/s")
    breadcrumb = "transfer / edit"
    success_url = reverse_lazy('dashboard:unassigned')
    form_class = TransferForm
    object = None

    def get_success_url(self):
        return reverse_lazy('transfer:id', args=[self.object.id])

    def get_object(self):
        if self.object:
            return self.object

        self.object = get_object_or_404(
            Transfer,
            owner=self.request.user.institution,
            id=self.kwargs.get("id"),
        )
        self.lot = self.object.lot_set.first()
        return self.object

    def get_initial(self):
        self.get_object()
        typ = {0: "desad", 1: "recadv"}
        return {
            'issuer_did': self.object.issuer_did,
            'did': self.object.organization_did,
            'name': self.object.organization_name,
            'reference': self.object.reference,
            'api_destination': self.object.api_destination,
            'token_destination': self.object.token_destination,
            'type_of_transfer': typ.get(self.object.type)
        }

    def get_form_kwargs(self):
        self.get_object()
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        kwargs['domain'] = "{}://{}".format(self.request.scheme, self.request.get_host())
        kwargs['lot'] = self.lot
        kwargs['instance'] = self.object

        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'lot': self.lot,
            'transfer': self.object,
            'lots_with_devices': self.lot.devices.exists(),
            'breadcrumb': self.breadcrumb,
            'title': self.title,
        })

        return context

    def form_valid(self, form):
        form.save()

        if form.instance:
            messages.success(self.request, _("Lot succesfully transfer"))
            self.transfer = form.instance
        else:
            messages.error(self.request, _("Error signing transaction"))

        response = super().form_valid(form)
        return response

    def form_invalid(self, form):
        messages.error(self.request, _("Lot error transfer"))
        response = super().form_invalid(form)
        return response



class DeviceView(DashboardView, TemplateView):
    template_name = "details.html"
    title = _("Device")
    breadcrumb = "Device / Details"

    def get(self, request, *args, **kwargs):
        self.id = kwargs['id']
        self.pk = kwargs['pk']
        self.transfer = get_object_or_404(
            Transfer,
            owner=self.request.user.institution,
            id=self.kwargs.get("id")
        )

        self.object = self.get_device()
        if self.object and not self.object.last_evidence:
            raise Http404

        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        self.object.initial()
        lot_tags = LotTag.objects.filter(owner=self.request.user.institution)
        dpps = []
        try:
            enviromental_impact_algorithm = Feia.run_environmental_impact_calculation()
            enviromental_impact = enviromental_impact_algorithm.get_device_environmental_impact(
                self.object
            )
        except Exception as err:
            logger.error("Enviromental Impact: {}".format(err))
            enviromental_impact = None

        uuids = [self.object.uuid]
        state_definitions = StateDefinition.objects.filter(
            institution=self.request.user.institution
        ).order_by('order')
        device_states = State.objects.filter(snapshot_uuid__in=uuids).order_by('-date')
        device_logs = DeviceLog.objects.filter(
            snapshot_uuid__in=uuids).order_by('-date')
        device_notes = Note.objects.filter(snapshot_uuid__in=uuids).order_by('-date')
        self.object.lots = [self.transfer]

        context.update({
            'object': self.object,
            'snapshot': self.object.last_evidence,
            'lot_tags': lot_tags,
            'dpps': dpps,
            'impact': enviromental_impact,
            "state_definitions": state_definitions,
            "device_states": device_states,
            "device_logs": device_logs,
            "device_notes": device_notes,
            "transfer": self.transfer,
        })
        return context

    def get_device(self):
        evidences = self.transfer.get_evidences()

        try:
            self.object = Device(id=self.pk, owner=self.request.user.institution)
            doc = evidences[self.pk]
            uuid= doc.get("uuid")
            evi = Evidence(uuid, doc=doc)
            evi.owner = self.transfer.owner

            if not evi.is_legacy():
                evi.semi_parser()
            evi.get_time()
            self.object.last_evidence = evi
            self.object.uuid = uuid
            self.object.uuids = [uuid]
            self.transfer.name = self.transfer.organization_name
            self.transfer.code = ""
            self.transfer.description = ""
            self.object._transfer = self.transfer
            return self.object
        except Exception:
            return


class TransferAddUserPropertyView(DeviceLogMixin, CreateView):
    template_name = "new_user_property.html"
    title = _("New User Property")
    breadcrumb = "Device / New Property"
    model = UserProperty
    fields = ("key", "value")

    def form_valid(self, form):
        form.instance.owner = self.request.user.institution
        form.instance.user = self.request.user
        form.instance.uuid = self.property.uuid
        form.instance.type = UserProperty.Type.USER

        try:
            response = super().form_valid(form)
            messages.success(self.request, _("Property successfully added."))
            log_message = _("<Created> UserProperty: {}: {}".format(
                form.instance.key,
                form.instance.value
            ))

            self.log_registry(form.instance.uuid, log_message)
            return response
        except IntegrityError:
            messages.error(self.request, _("Property is already defined."))
            return self.form_invalid(form)

    def get_form_kwargs(self):
        self.id = self.kwargs['id']
        self.pk = self.kwargs['pk']
        self.transfer = get_object_or_404(
            Transfer,
            owner=self.request.user.institution,
            id=self.kwargs.get("id")
        )

        self.property = self.get_device()
        if not self.property:
            raise Http404

        self.property.transfer = self.transfer
        return super().get_form_kwargs()

    def get_success_url(self):
        return reverse_lazy('transfer:device', args=[self.id, self.pk]) + "#user_properties"

    def get_device(self):
        evidences = self.transfer.get_evidences()

        # try:
        self.property = Device(id=self.pk)
        doc = evidences[self.pk]
        uuid= doc.get("uuid")
        evi = Evidence(uuid, doc=doc)
        evi.owner = self.transfer.owner

        if not evi.is_legacy():
            evi.semi_parser()
        evi.get_time()
        self.property.last_evidence = evi
        self.property.uuid = uuid
        self.transfer.name = self.transfer.destination_name
        self.transfer.code = ""
        self.transfer.description = ""
        return self.property
        # except Exception:
        #     return

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["object"] = self.property
        context["transfer"] = self.transfer
        return context

class TransferDeleteUserPropertyView(DeleteUserPropertyView):

    def get_success_url(self):
        id = self.kwargs.get('id')
        pk = self.kwargs.get('device_id')
        return reverse_lazy('transfer:device', args=[id, pk]) + "#user_properties"

class TransferUpdateUserPropertyView(UpdateUserPropertyView):

    def get_success_url(self):
        id = self.kwargs.get('id')
        pk = self.kwargs.get('device_id')
        return reverse_lazy('transfer:device', args=[id, pk]) + "#user_properties"


class DeleteTransferView(DashboardView, TemplateView):
    template_name = "delete_transfer.html"
    title = _("Delete transfer")
    breadcrumb = "transfer / Delete"
    object = None

    def get(self, request, *args, **kwargs):
        self.get_object()
        context = {
            'lot': self.lot,
            'object': self.object,
            'breadcrumb': self.breadcrumb,
            'title': self.title,
        }
        return render(request, self.template_name, context)

    def post(self, request, *args, **kwargs):
        self.get_object()

        self.object.delete()
        messages.success(request, _("Transfer succesfully deleted"))
        return redirect(self.get_success_url())

    def get_object(self):
        if self.object:
            return self.object

        self.object = get_object_or_404(
            Transfer,
            owner=self.request.user.institution,
            id=self.kwargs.get("id"),
            sended=False
        )
        self.lot = self.object.lot_set.first()
        return self.object

    def get_success_url(self):
        return reverse_lazy('dashboard:lot', args=[self.lot.id])


class DownloadTransferView(DashboardView, TemplateView):
    def get(self, request, *args, **kwargs):
        self.id = self.kwargs.get("id")
        self.object = get_object_or_404(
            Transfer,
            owner=self.request.user.institution,
            id=self.id,
        )
        response = HttpResponse(self.object.str_credential, content_type="application/json")
        response['Content-Disposition'] = 'attachment; filename={}'.format("credential.json")
        return response
