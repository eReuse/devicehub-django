from django.urls import path, include
from action import views

app_name = 'action'

urlpatterns = [

    path("new/", views.ChangeStateView.as_view(), name="change_state"),
    path("dismantle/<str:pk>/", views.DismantleDeviceView.as_view(), name="dismantle_device"),
    path('new/bulk/<int:pk>', views.BulkStateChangeView.as_view(), name='bulk_change_state'),
    path('note/add/', views.AddNoteView.as_view(), name='add_note'),
    path('note/edit/<int:pk>', views.UpdateNoteView.as_view(), name='update_note'),
    path('note/delete/<int:pk>', views.DeleteNoteView.as_view(), name='delete_note'),
]
