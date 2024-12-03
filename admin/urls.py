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
    path("states/", views.StatesPanelView.as_view(), name="states"),
    path("states/add", views.AddStateDefinitionView.as_view(), name="add_state_definition"),
    path('states/delete/<int:pk>', views.DeleteStateDefinitionView.as_view(), name='delete_state_definition'),
    path('states/update_order/', views.UpdateStateOrderView.as_view(), name='update_state_order'),
]
