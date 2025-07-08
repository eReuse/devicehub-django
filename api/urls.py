import os

from pathlib import Path

from django.urls import path
from django.views.generic import TemplateView
from django.views.static import serve
from django.urls import re_path

from api import views


app_name = 'api'
BASE_DIR = Path(__file__).resolve().parent.parent


urlpatterns = [
    path('v1/snapshot/', views.NewSnapshotView.as_view(), name='new_snapshot'),
    path('v1/property/<str:pk>/', views.AddPropertyView.as_view(), name='new_property'),
    path('v1/device/<str:pk>/', views.DetailsDeviceView.as_view(), name='device'),
    path('v1/tokens/', views.TokenView.as_view(), name='tokens'),
    path('v1/tokens/new', views.TokenNewView.as_view(), name='new_token'),
    path("v1/tokens/<int:pk>/edit", views.EditTokenView.as_view(), name="edit_token"),
    path('v1/tokens/<int:pk>/del', views.TokenDeleteView.as_view(), name='delete_token'),
    path("openapi.json", views.openapi_json),
    path("docs/", TemplateView.as_view(template_name="swagger-ui/index.html")),
    re_path(r"^swagger-ui/(?P<path>.*)$", serve, {
        "document_root": os.path.join(BASE_DIR, "static/swagger-ui"),
    }),
]
