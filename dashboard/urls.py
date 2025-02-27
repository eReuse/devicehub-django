from django.urls import path
from dashboard import views

app_name = 'dashboard'

urlpatterns = [
    path("all", views.AllDevicesView.as_view(), name="all_device"),
    path("search", views.SearchView.as_view(), name="search"),
]
