from django.urls import path
from device import views

app_name = 'device'

urlpatterns = [
    path("add/", views.NewDeviceView.as_view(), name="add"),
    path("<int:pk>/", views.DetailsView.as_view(), name="details"),
    path("physical/<int:pk>/", views.PhysicalView.as_view(), name="physical_edit"),
]
