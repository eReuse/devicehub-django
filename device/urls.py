from django.urls import path
from device import views

app_name = 'device'

urlpatterns = [
    path("add/", views.NewDeviceView.as_view(), name="add"),
    path("edit/<str:pk>/", views.EditDeviceView.as_view(), name="edit"),
    path("<str:pk>/", views.DetailsView.as_view(), name="details"),
    path("<str:pk>/annotation/add", views.AddAnnotationView.as_view(), name="add_annotation"),
]
