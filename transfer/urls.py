from django.urls import path
from transfer import views

app_name = 'transfer'

urlpatterns = [
    path("add/<int:lot_id>", views.NewTransferView.as_view(), name="add"),
    path("sended/", views.TransferSendedView.as_view(), name="sended"),
    path("received/", views.TransferReceivedView.as_view(), name="received"),
    path("<int:id>", views.TransferView.as_view(), name="id"),
    path("<int:id>/ref/<int:reference>", views.TransferView.as_view(), name="reference"),
    path("<int:id>/edit", views.EditTransferView.as_view(), name="edit"),
    path("<int:id>/send", views.SendTransferView.as_view(), name="send"),
    path("<int:id>/download", views.DownloadTransferView.as_view(), name="download"),
    path("<int:id>/delete", views.DeleteTransferView.as_view(), name="delete"),
    path("<int:id>/device/<str:pk>", views.DeviceView.as_view(), name="device"),
    path("<int:id>/device/<str:pk>/property/add",
         views.TransferAddUserPropertyView.as_view(), name="add_user_property"),
    path("<int:id>/device/<str:device_id>/property/del/<int:pk>",
         views.TransferDeleteUserPropertyView.as_view(), name="del_user_property"),
    path("<int:id>/device/<str:device_id>/property/<int:pk>/del",
         views.TransferUpdateUserPropertyView.as_view(), name="update_user_property"),
]
