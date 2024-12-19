from django.urls import path, include
from action import views

app_name = 'action'

urlpatterns = [

    path("new/", views.ChangeStateView.as_view(), name="change_state"),
    path('state/<int:pk>/undo/', views.UndoStateView.as_view(), name='undo_state'),
    path('note/add/', views.AddNoteView.as_view(), name='add_note'),

]
