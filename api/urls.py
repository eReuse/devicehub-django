from api import views

from django.urls import path


app_name = 'api'

urlpatterns = [
    path('snapshot/', views.NewSnapshot, name='new_snapshot'),
    path('tokens/', views.TokenView.as_view(), name='tokens'),
    path('tokens/new', views.TokenNewView.as_view(), name='new_token'),
    path('tokens/<int:pk>/del', views.TokenDeleteView.as_view(), name='delete_token'),
]
