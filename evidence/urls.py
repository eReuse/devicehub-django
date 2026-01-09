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
    path("import", views.ImportView.as_view(), name="import"),
    path("photo", views.ImportPhotoView.as_view(), name="photo"),
    path("<uuid:pk>", views.EvidenceView.as_view(), name="details"),
    path("<uuid:pk>/eraseserver", views.EraseServerView.as_view(), name="erase_server"),
    path("<uuid:pk>/download", views.DownloadEvidenceView.as_view(), name="download"),
    path("<uuid:pk>/photo", views.PhotoEvidenceView.as_view(), name="photo_file"),
    path("alias/<str:pk>/<uuid:snapshot_id>/delete", views.DeleteEvidenceAliasView.as_view(), name="delete_alias"),
    path("tag/<str:pk>/delete", views.DeleteEvidenceAliasView.as_view(), name="delete_tag"),

    path('credential/<int:pk>/', views.CredentialDetailView.as_view(), name='credential_detail'),
    path('credential/<int:pk>/download/', views.DownloadDPPView.as_view(), name='download_dpp'),
    path('credential/<int:pk>/validate/', views.ValidateDPPView.as_view(), name='validate_dpp'),
    path('credential/by-evidence/<uuid:uuid>/', views.CredentialByEvidenceUUIDView.as_view(), name='credential_by_evidence')

]
