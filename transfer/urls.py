from django.urls import path
from transfer import views

app_name = 'transfer'

urlpatterns = [
    path("add/", views.NewTransferView.as_view(), name="add"),
    path("sended/", views.TransferSendedView.as_view(), name="sended"),
    path("received/", views.TransferReceivedView.as_view(), name="received"),
    path("<int:id>", views.TransferView.as_view(), name="id"),
    path("<int:id>/device/<str:pk>", views.DeviceView.as_view(), name="device"),
    path("<int:id>/device/<str:pk>/property/add",
         views.TransferAddUserPropertyView.as_view(), name="add_user_property"),
    path("<int:id>/device/<str:device_id>/property/del/<int:pk>",
         views.TransferDeleteUserPropertyView.as_view(), name="del_user_property"),
    path("<int:id>/device/<str:device_id>/property/<int:pk>/del",
         views.TransferUpdateUserPropertyView.as_view(), name="update_user_property"),
]
