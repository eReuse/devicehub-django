from django.urls import path
from dashboard import views 

app_name = 'dashboard'

urlpatterns = [
    path("", views.UnassignedDevicesView.as_view(), name="unassigned_devices"),
]
