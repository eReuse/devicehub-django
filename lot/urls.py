from django.urls import path
from lot import views

app_name = 'lot'

urlpatterns = [
    path("add/", views.NewLotView.as_view(), name="add"),
    path("edit/<int:pk>/", views.EditLotView.as_view(), name="edit"),
    path("add/devices/", views.AddToLotView.as_view(), name="add_devices"),
]
