from django.urls import path
from dashboard import views

app_name = 'dashboard'

urlpatterns = [
    path("", views.UnassignedDevicesView.as_view(), name="unassigned"),
    path("all", views.AllDevicesView.as_view(), name="all_device"),
    path("inventory", views.InventoryOverviewView.as_view(), name="inventory"),
    path("<int:pk>/", views.LotDashboardView.as_view(), name="lot"),
    path("search", views.SearchView.as_view(), name="search"),
]
