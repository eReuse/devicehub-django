from django.urls import path
from user import views

app_name = 'user'

urlpatterns = [
    path("panel/", views.PanelView.as_view(), name="panel"),
    path("settings/", views.SettingsView.as_view(), name="settings"),
    path('<int:pk>/', views.UserProfileView.as_view(), name='profile'),
    path('v1/tokens/', views.TokenView.as_view(), name='tokens'),
    path('v1/tokens/new', views.TokenNewView.as_view(), name='new_token'),
    path("v1/tokens/<int:pk>/edit", views.EditTokenView.as_view(), name="edit_token"),
    path('v1/tokens/<int:pk>/del', views.TokenDeleteView.as_view(), name='delete_token'),
]
