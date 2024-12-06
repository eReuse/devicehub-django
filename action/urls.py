from django.urls import path, include
from action import views

app_name = 'action'

urlpatterns = [

    path("new/", views.NewActionView.as_view(), name="new_action"),
    path('state/<int:pk>/undo/', views.ActionUndoView.as_view(), name='undo_action'),

]
