# from django.urls import path, include
# from rest_framework.routers import DefaultRouter
# from snapshot.views import SnapshotViewSet

# router = DefaultRouter()
# router.register(r'snapshots', SnapshotViewSet)

# urlpatterns = [
#     path('', include(router.urls)),
# ]
from django.urls import path
from evidence import views 

app_name = 'evidence'

urlpatterns = [
    path("", views.ListEvidencesView.as_view(), name="list"),
    path("upload", views.UploadView.as_view(), name="upload"),
    path("<uuid:pk>", views.EvidenceView.as_view(), name="details"),
    path("<uuid:pk>/download", views.DownloadEvidenceView.as_view(), name="download"),
]
