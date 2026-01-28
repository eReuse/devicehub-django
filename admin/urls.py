from django.urls import path
from admin import views

app_name = 'admin'

urlpatterns = [
    path("panel/", views.PanelView.as_view(), name="panel"),
    path("users/", views.UsersView.as_view(), name="users"),
    path("users/new", views.CreateUserView.as_view(), name="new_user"),
    path("users/edit/<int:pk>", views.EditUserView.as_view(), name="edit_user"),
    path("users/delete/<int:pk>", views.DeleteUserView.as_view(), name="delete_user"),
    path("institution/<int:pk>", views.InstitutionView.as_view(), name="institution"),
    path('institution/<int:pk>/label-settings/', views.InstitutionLabelCustomizationView.as_view(), name='label_settings'),
    path("institution/<int:pk>/settings", views.InstitutionConfigView.as_view(), name="institution_settings"),
    path("institution/<int:pk>/dfr/issue", views.IssueDigitalFacilityRecordView.as_view(), name="institution_dfr_issue"),

    path("states/", views.StatesPanelView.as_view(), name="states_panel"),
    path("states/add", views.AddStateDefinitionView.as_view(), name="add_state_definition"),
    path("states/delete/<int:pk>", views.DeleteStateDefinitionView.as_view(), name='delete_state_definition'),
    path("states/update_order/", views.UpdateStateOrderView.as_view(), name='update_state_order'),
    path("states/edit/<int:pk>/", views.UpdateStateDefinitionView.as_view(), name='edit_state_definition'),
    path("lot/", views.LotTagPanelView.as_view(), name="tag_panel"),
    path("lot/add", views.AddLotTagView.as_view(), name="add_lot_tag"),
    path("lot/delete/<int:pk>", views.DeleteLotTagView.as_view(), name='delete_lot_tag'),
    path("lot/edit/<int:pk>/", views.UpdateLotTagView.as_view(), name='edit_lot_tag'),
    path("lot/update_order/", views.UpdateLotTagOrderView.as_view(), name='update_lot_tag_order'),
    path("product-types/", views.DeviceTypesPanelView.as_view(), name="devicetypes_panel"),
    path("product-types/add", views.AddDeviceTypeView.as_view(), name="add_device_type"),
    path("product-types/delete/<int:pk>", views.DeleteDeviceTypeView.as_view(), name='delete_device_type'),
    path("product-types/update_order/", views.UpdateDeviceTypeOrderView.as_view(), name='update_device_type_order'),
    path("product-types/edit/<int:pk>/", views.UpdateDeviceTypeView.as_view(), name='edit_device_type'),
    path("product-types/<int:type_pk>/attributes/", views.DeviceTypeAttributesPanelView.as_view(), name="attributes_panel"),
    path("product-types/<int:type_pk>/attributes/add", views.AddDeviceTypeAttributeView.as_view(), name="add_device_type_attribute"),
    path("product-types/attributes/edit/<int:pk>/", views.UpdateDeviceTypeAttributeView.as_view(), name='edit_device_type_attribute'),
    path("product-types/attributes/delete/<int:pk>", views.DeleteDeviceTypeAttributeView.as_view(), name='delete_device_type_attribute'),
    path("product-types/<int:type_pk>/attributes/update_order/", views.UpdateDeviceTypeAttributeOrderView.as_view(), name='update_device_type_attribute_order'),
]
