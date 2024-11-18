from django.urls import path
from dpp import views 

app_name = 'dpp'

urlpatterns = [
    path("<int:proof_id>/", views.LotDashboardView.as_view(), name="proof"),
]
