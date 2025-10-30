import logging

from django.contrib import messages
from django.urls import reverse_lazy
from django.views.generic.edit import FormView
from django.utils.translation import gettext_lazy as _
from django_tables2 import SingleTableView

from dashboard.mixins import DashboardView
from lot.forms import TransferForm
from lot.models import Lot
from transfer.models import Transfer
from transfer.tables import TransferTable


logger = logging.getLogger(__name__)


class TransferTagView(DashboardView, SingleTableView):
    template_name = "lots.html"
    title = _("Transfers")
    breadcrumb = _("transfers") + " / "
    success_url = reverse_lazy('dashboard:unassigned')
    model = Transfer
    table_class = TransferTable
    paginate_by = 10

    def get_queryset(self):
        return self.model.objects.filter(owner=self.request.user.institution)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'title': self.title + " - " + self.tag.name,
            'breadcrumb': self.breadcrumb + self.tag.name,
            'show_archived': self.show_archived,
            'search_query': self.search_query,
            'total_count': self.get_queryset.count(),
        })
        return context


# class TransferLotsView(LotSuccessUrlMixin, DashboardView, FormView):
#     template_name = "transfer_lots.html"
#     title = _("Transfer lot/s")
#     breadcrumb = "lots / Transfer"
#     form_class = TransferForm
#     lots = []

#     def get(self, request, *args, **kwargs):
#         selected_ids = self.request.GET.getlist('select')
#         if not selected_ids:
#              messages.error(self.request, _("Not lots selected for transfer"))

#         self.lots = Lot.objects.filter(
#             id__in=selected_ids,
#             owner=self.request.user.institution
#         )
#         for lot in self.lots:
#             if lot.transfer:
#                 txt = _("Error lot {} have a transfer")
#                 messages.error(self.request, txt.format(lot.name))
#         return super().get(request, *args, **kwargs)

#     def get_success_url(self):
#         return reverse_lazy('dashboard:unassigned')

#     def get_context_data(self, **kwargs):
#         context = super().get_context_data(**kwargs)
#         context.update({
#             'lots': self.lots,
#             'lots_with_devices': any(lot.devices.exists() for lot in self.lots),
#             'breadcrumb': self.breadcrumb,
#             'title': self.title,
#         })

#         return context

#     def get_form_kwargs(self):
#         kwargs = super().get_form_kwargs()
#         kwargs['user'] = self.request.user
#         kwargs['website'] = "{}://{}".format(self.request.scheme, self.request.get_host())
#         kwargs['initial']['selected_ids'] = self.request.GET.getlist('select') or []
#         return kwargs

#     def form_valid(self, form):
#         form.save()

#         if form.instance:
#             messages.success(self.request, _("Lots succesfully transfer"))
#         else:
#             messages.error(self.request, _("Error signing transaction"))

#         response = super().form_valid(form)
#         return response

#     def form_invalid(self, form):
#         messages.error(self.request, _("Lots error transfer"))
#         response = super().form_invalid(form)
#         return response


class NewTransferView(DashboardView, FormView):
    template_name = "transfer_lots.html"
    title = _("Transfer lot/s")
    breadcrumb = "lots / Transfer"
    success_url = reverse_lazy('dashboard:unassigned')
    form_class = TransferForm
    lots = []

    def get(self, request, *args, **kwargs):
        selected_ids = self.request.GET.getlist('select')
        if not selected_ids:
             messages.error(self.request, _("Not lots selected for transfer"))

        self.lots = Lot.objects.filter(
            id__in=selected_ids,
            owner=self.request.user.institution
        )
        for lot in self.lots:
            if lot.transfer:
                txt = _("Error lot {} have a transfer")
                messages.error(self.request, txt.format(lot.name))
        return super().get(request, *args, **kwargs)

    def get_success_url(self):
        return reverse_lazy('dashboard:unassigned')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'lots': self.lots,
            'lots_with_devices': any(lot.devices.exists() for lot in self.lots),
            'breadcrumb': self.breadcrumb,
            'title': self.title,
        })

        return context

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        kwargs['website'] = "{}://{}".format(self.request.scheme, self.request.get_host())
        kwargs['initial']['selected_ids'] = self.request.GET.getlist('select') or []
        return kwargs

    def form_valid(self, form):
        form.save()

        if form.instance:
            messages.success(self.request, _("Lots succesfully transfer"))
        else:
            messages.error(self.request, _("Error signing transaction"))

        response = super().form_valid(form)
        return response

    def form_invalid(self, form):
        messages.error(self.request, _("Lots error transfer"))
        response = super().form_invalid(form)
        return response
