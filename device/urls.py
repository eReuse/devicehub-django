from django.urls import path
from device import views

app_name = 'device'

urlpatterns = [
    path("add/", views.NewDeviceView.as_view(), name="add"),
    path("edit/<int:pk>/", views.EditDeviceView.as_view(), name="edit"),
    path("<int:pk>/", views.DetailsView.as_view(), name="details"),
    path("<int:pk>/annotation/add", views.AddAnnotationView.as_view(), name="add_annotation"),
]
