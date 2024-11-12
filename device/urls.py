from django.urls import path
from device import views

app_name = 'device'

urlpatterns = [
    path("add/", views.NewDeviceView.as_view(), name="add"),
    path("edit/<str:pk>/", views.EditDeviceView.as_view(), name="edit"),
    path("<str:pk>/", views.DetailsView.as_view(), name="details"),
    path("<str:pk>/user_property/add", views.AddUserPropertyView.as_view(), name="add_user_property"),
    path("<str:pk>/document/add", views.AddDocumentView.as_view(), name="add_document"),
    path("<str:pk>/public/", views.PublicDeviceWebView.as_view(), name="device_web"),

]
