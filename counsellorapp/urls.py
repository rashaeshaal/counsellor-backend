from django.urls import path

from .views import UpcomingSessionsView, RecentActivityView, CounsellorProfileView, CounsellorPaymentSettingsView,CounsellorPaymentDetailView

from rest_framework_simplejwt.views import TokenRefreshView

urlpatterns = [
    path('upcoming-sessions/', UpcomingSessionsView.as_view(), name='upcoming-sessions'),
    path('recent-activity/', RecentActivityView.as_view(), name='recent-activity'),
    path('profile/', CounsellorProfileView.as_view(), name='counsellor-profile'),
    path('payment-settings/<int:user_id>/', CounsellorPaymentDetailView.as_view(), name='counsellor-payment-settings'),
    path('payment-settings/', views.CounsellorPaymentSettingsView.as_view(), name='payment-settings'),
    path('status/', views.CounsellorStatusView.as_view(), name='counsellor-status'),
]
