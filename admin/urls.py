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
    path("institution/<int:pk>/settings", views.InstitutionConfigView.as_view(), name="institution_settings"),
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
]
