#see dhub/urls.py

from api import views

from django.urls import path


app_name = 'api'

urlpatterns = [
    path('v1/snapshot/', views.NewSnapshotView.as_view(), name='new_snapshot'),
    path('v1/property/<str:pk>/', views.AddPropertyView.as_view(), name='new_property'),
    path('v1/device/<str:pk>/', views.DetailsDeviceView.as_view(), name='device'),

]
