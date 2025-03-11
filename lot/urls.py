from django.urls import path
from lot import views

app_name = 'lot'

urlpatterns = [
    path("add/", views.NewLotView.as_view(), name="add"),
    path("lots/delete/", views.DeleteLotsView.as_view(), name="delete"),
    path("edit/<int:pk>/", views.EditLotView.as_view(), name="edit"),
    path("add/devices/", views.AddToLotView.as_view(), name="add_devices"),
    path("del/devices/", views.DelToLotView.as_view(), name="del_devices"),
    path("group/<int:pk>/", views.LotsTagsView.as_view(), name="tags"),
    path("<int:pk>/property", views.LotPropertiesView.as_view(), name="properties"),
    path("<int:pk>/property/add", views.AddLotPropertyView.as_view(), name="add_property"),
    path("<int:pk>/property/update", views.UpdateLotPropertyView.as_view(), name="update_property"),
    path("<int:pk>/property/delete", views.DeleteLotPropertyView.as_view(), name="delete_property"),
    path("<int:pk>/subscription/", views.SubscriptLotView.as_view(), name="subscription"),
    path("<int:pk>/unsubscription/<int:id>", views.UnsubscriptLotView.as_view(), name="unsubscription"),
    path("<int:pk>/donor/add", views.AddDonorView.as_view(), name="add_donor"),
    path("<int:pk>/donor/del", views.DelDonorView.as_view(), name="del_donor"),
    path("<int:pk>/donor/<uuid:id>", views.DonorView.as_view(), name="web_donor"),
    path("<int:pk>/donor/<uuid:id>/accept", views.AcceptDonorView.as_view(), name="accept_donor"),
]
