from django.urls import path
from lot import views

app_name = 'lot'

urlpatterns = [
    path("add/", views.NewLotView.as_view(), name="add"),
    path("lots/delete/", views.DeleteLotsView.as_view(), name="delete"),
    path("edit/<int:pk>/", views.EditLotView.as_view(), name="edit"),
    path("add/devices/", views.AddToLotView.as_view(), name="add_devices"),
    path('lot/<int:pk>/unassign-devices/', views.DelToLotView.as_view(), name='del_devices'),
    path("group/<int:pk>/", views.LotsTagsView.as_view(), name="tags"),
    path("<int:pk>/property", views.LotPropertiesView.as_view(), name="properties"),
    path("<int:pk>/property/add", views.AddLotPropertyView.as_view(), name="add_property"),
    path("<int:pk>/property/update", views.UpdateLotPropertyView.as_view(), name="update_property"),
    path("<int:pk>/property/delete", views.DeleteLotPropertyView.as_view(), name="delete_property"),
]
