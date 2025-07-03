from api import views

from django.urls import path, re_path
from django.urls import path


app_name = 'api'

urlpatterns = [
    path('v1/snapshot/', views.NewSnapshotView.as_view(), name='new_snapshot'),
    path('v1/device/<str:pk>/', views.DetailsDeviceView.as_view(), name='device'),
    path('v1/tokens/', views.TokenView.as_view(), name='tokens'),
    path('v1/tokens/new', views.TokenNewView.as_view(), name='new_token'),
    path("v1/tokens/<int:pk>/edit", views.EditTokenView.as_view(), name="edit_token"),
    path('v1/tokens/<int:pk>/del', views.TokenDeleteView.as_view(), name='delete_token'),
    #either lot id or lot name
    re_path(r'^v1/lots/(?P<identifier>.+)/devices/$', views.LotDevicesAPIView.as_view()),
    path('v1/devices/<str:pk>/properties/<str:key>/', views.UpdateDevicePropertyView.as_view(),name='new_or_update_property'),
]
