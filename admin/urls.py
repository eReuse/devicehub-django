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
    path("lot_tag/", views.LotTagPanelView.as_view(), name="tag_panel"),
    path("lot_tag/add", views.AddLotTagView.as_view(), name="add_lot_tag"),
    path("lot_tag/delete/<int:pk>", views.DeleteLotTagView.as_view(), name='delete_lot_tag'),
    path("lot_tag/edit/<int:pk>/", views.UpdateLotTagView.as_view(), name='edit_lot_tag'),
]
