from django.urls import path
from device import views

app_name = 'device'

urlpatterns = [
    path("add/", views.NewDeviceView.as_view(), name="add"),
    path("edit/<str:pk>/", views.EditDeviceView.as_view(), name="edit"),
    path("<str:pk>/", views.DetailsView.as_view(), name="details"),
    path("<str:pk>/user_property/add",
         views.AddUserPropertyView.as_view(), name="add_user_property"),
    path("<str:device_id>/user_property/<int:pk>/delete",
         views.DeleteUserPropertyView.as_view(), name="delete_user_property"),
    path("<str:device_id>/user_property/<int:pk>/update",
         views.UpdateUserPropertyView.as_view(), name="update_user_property"),
    path("<str:pk>/public/", views.PublicDeviceWebView.as_view(), name="device_web"),
    path('<str:pk>/export-environmental-impact-pdf/',
         views.ExportEnvironmentalImpactPDF.as_view(), name='export_environmental_impact_pdf'),

]
