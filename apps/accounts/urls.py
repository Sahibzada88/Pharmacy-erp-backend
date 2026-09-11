from django.urls import path
from .views import LoginView, MeView, StaffListCreateView, StaffDetailView, ChangePasswordView

urlpatterns = [
    path('login/', LoginView.as_view(), name='login'),
    path('me/', MeView.as_view(), name='me'),
    path('staff/', StaffListCreateView.as_view(), name='staff-list-create'),
    path('staff/<int:pk>/', StaffDetailView.as_view(), name='staff-detail'),
    path('change-password/', ChangePasswordView.as_view(), name='change-password'),
]
