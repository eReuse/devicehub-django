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
    path("<int:pk>/participants", views.ParticipantsView.as_view(), name="participants"),
    path("<int:pk>/property/add", views.AddLotPropertyView.as_view(), name="add_property"),
    path("<int:pk>/property/update", views.UpdateLotPropertyView.as_view(), name="update_property"),
    path("<int:pk>/property/delete", views.DeleteLotPropertyView.as_view(), name="delete_property"),
    path("<int:pk>/subscription/", views.SubscriptLotView.as_view(), name="subscription"),
    path("<int:pk>/unsubscription/<int:id>", views.UnsubscriptLotView.as_view(), name="unsubscription"),
    path("<int:pk>/donor/add", views.AddDonorView.as_view(), name="add_donor"),
    path("<int:pk>/donor/del", views.DelDonorView.as_view(), name="del_donor"),
    path("<int:pk>/donor/<uuid:id>", views.DonorView.as_view(), name="web_donor"),
    path("<int:pk>/donor/<uuid:id>/accept", views.AcceptDonorView.as_view(), name="accept_donor"),
    path("<int:pk>/donor/<uuid:id>/export/<str:mime>", views.ExportDonorView.as_view(), name="export_donor"),
    path("<int:pk>/beneficiary", views.BeneficiaryView.as_view(), name="beneficiary"),
    path("<int:pk>/beneficiary/<uuid:id>/del", views.DeleteBeneficiaryView.as_view(), name="del_beneficiary"),
    path("<int:pk>/beneficiary/<uuid:id>/devices", views.ListDevicesBeneficiaryView.as_view(), name="devices_beneficiary"),
    path("<int:pk>/beneficiary/<uuid:id>/devices/<str:dev_id>/del", views.DelDeviceBeneficiaryView.as_view(), name="del_device_beneficiary"),
    path("<int:pk>/beneficiary/<uuid:id>/devices/add", views.AddDevicesBeneficiaryView.as_view(), name="add_device_beneficiary"),
    path("<int:pk>/beneficiary/<uuid:id>/", views.WebBeneficiaryView.as_view(), name="web_beneficiary"),
    path("<int:pk>/beneficiary/<uuid:id>/agreement", views.AgreementBeneficiaryView.as_view(), name="agreement_beneficiary"),
    path("<int:pk>/beneficiary/<uuid:id>/accept", views.AcceptBeneficiaryView.as_view(), name="accept_beneficiary"),
]
