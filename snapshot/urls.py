from django.urls import path, include
from rest_framework.routers import DefaultRouter
from snapshot.views import SnapshotViewSet

router = DefaultRouter()
router.register(r'snapshots', SnapshotViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
