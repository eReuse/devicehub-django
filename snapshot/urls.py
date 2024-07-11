# from django.urls import path, include
# from rest_framework.routers import DefaultRouter
# from snapshot.views import SnapshotViewSet

# router = DefaultRouter()
# router.register(r'snapshots', SnapshotViewSet)

# urlpatterns = [
#     path('', include(router.urls)),
# ]
from django.urls import path
from snapshot import views 

app_name = 'snapshot'

urlpatterns = [
    path("", views.ListSnapshotsView.as_view(), name="list"),
]
