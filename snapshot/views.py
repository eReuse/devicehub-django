from django.utils.translation import gettext_lazy as _
from django.views.generic.base import TemplateView
from dashboard.mixins import  DashboardView
from snapshot.models import Snapshot
# from django.shortcuts import render
# from rest_framework import viewsets
# from snapshot.serializers import SnapshotSerializer


# class SnapshotViewSet(viewsets.ModelViewSet):
#     queryset = Snapshot.objects.all()
#     serializer_class = SnapshotSerializer


class ListSnapshotsView(DashboardView, TemplateView):
    template_name = "snapshots.html"
    section = "snapshots"
    title = _("Snapshots")
    breadcrumb = "Snapshots"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        snapshots = Snapshot.objects.filter(owner=self.request.user)
        context.update({
            'snapshots': snapshots,
        })
        return context
