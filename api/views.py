import json

from django.urls import reverse_lazy
from django.shortcuts import get_object_or_404, redirect
from django.utils.translation import gettext_lazy as _
from django.views.decorators.csrf import csrf_exempt
from django.core.exceptions import ValidationError
from django_tables2 import SingleTableView
from django.views.generic.base import View
from django.views.generic.edit import (
    CreateView,
    DeleteView,
    UpdateView,
)
from django.http import JsonResponse
from uuid import uuid4

from dashboard.mixins import DashboardView
from evidence.models import Annotation
from evidence.parse import Build
from user.models import User
from api.models import Token
from api.tables import TokensTable


def save_in_disk(data, user):
    pass


@csrf_exempt
def NewSnapshot(request):
    # Accept only posts
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid request method'}, status=400)

    # Authentication
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        return JsonResponse({'error': 'Invalid or missing token'}, status=401)

    token = auth_header.split(' ')[1]
    tk = Token.objects.filter(token=token).first()
    if not tk:
        return JsonResponse({'error': 'Invalid or missing token'}, status=401)

    # Validation snapshot
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    # try:
    #     Build(data, None, check=True)
    # except Exception:
    #     return JsonResponse({'error': 'Invalid Snapshot'}, status=400)

    exist_annotation = Annotation.objects.filter(
        uuid=data['uuid']
    ).first()

    if exist_annotation:
        raise ValidationError("error: the snapshot {} exist".format(data['uuid']))

    # Process snapshot
    # save_in_disk(data, tk.user)

    try:
        Build(data, tk.user)
    except Exception:
        return JsonResponse({'status': 'fail'}, status=200)

    return JsonResponse({'status': 'success'}, status=200)




class TokenView(DashboardView, SingleTableView):
    template_name = "token.html"
    title = _("Credential management")
    section = "Credential"
    subtitle = _('Managament Tokens')
    icon = 'bi bi-key'
    model = Token
    table_class = TokensTable

    def get_queryset(self):
        """
        Override the get_queryset method to filter events based on the user type.
        """
        return Token.objects.filter().order_by("-id")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'tokens': Token.objects.all(),
        })
        return context


class TokenDeleteView(DashboardView, DeleteView):
    model = Token

    def get(self, request, *args, **kwargs):
        self.pk = kwargs['pk']
        self.object = get_object_or_404(self.model, pk=self.pk, owner=self.request.user)
        self.object.delete()

        return redirect('api:tokens')


class TokenNewView(DashboardView, CreateView):
    template_name = "new_token.html"
    title = _("Credential management")
    section = "Credential"
    subtitle = _('New Tokens')
    icon = 'bi bi-key'
    model = Token
    success_url = reverse_lazy('api:tokens')
    fields = (
        "tag",
    )

    def form_valid(self, form):
        form.instance.owner = self.request.user
        form.instance.token = uuid4()
        return super().form_valid(form)


class EditTokenView(DashboardView, UpdateView):
    template_name = "new_token.html"
    title = _("Credential management")
    section = "Credential"
    subtitle = _('New Tokens')
    icon = 'bi bi-key'
    model = Token
    success_url = reverse_lazy('api:tokens')
    fields = (
        "tag",
    )

    def get_form_kwargs(self):
        pk = self.kwargs.get('pk')
        self.object = get_object_or_404(
            self.model,
            owner=self.request.user,
            pk=pk,
        )
        kwargs = super().get_form_kwargs()
        return kwargs
