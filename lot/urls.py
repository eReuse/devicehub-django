from django.urls import path
from lot import views

app_name = 'lot'

urlpatterns = [
    path("add/", views.NewLotView.as_view(), name="add"),
    path("delete/<int:pk>/", views.DeleteLotView.as_view(), name="delete"),
    path("edit/<int:pk>/", views.EditLotView.as_view(), name="edit"),
    path("add/devices/", views.AddToLotView.as_view(), name="add_devices"),
    path("del/devices/", views.DelToLotView.as_view(), name="del_devices"),
    path("temporal/", views.LotsTemporalView.as_view(), name="lots_temporal"),
    path("outgoing/", views.LotsOutgoingView.as_view(), name="lots_outgoing"),
    path("incoming/", views.LotsIncomingView.as_view(), name="lots_incoming"),
]
