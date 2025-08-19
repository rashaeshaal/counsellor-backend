# urls.py
from django.urls import path, include
from rest_framework_simplejwt.views import TokenRefreshView
from . import views

urlpatterns = [
    # Authentication URLs

    path('auth/token/refresh/', TokenRefreshView.as_view(), name='token-refresh'),
    # Counsellor URLs

    path('profile/', views.CounsellorProfileView.as_view(), name='counsellor-profile'),
    path('status/', views.CounsellorStatusView.as_view(), name='counsellor-status'),
    path('payment-settings/', views.CounsellorPaymentSettingsView.as_view(), name='payment-settings'),
    path('payment-settings/<int:user_id>/', views.CounsellorPaymentDetailView.as_view(), name='payment-settings-detail'),
    path('status/<int:booking_id>/', views.CallStatusView.as_view(), name='call-status'),
    path('accept/', views.AcceptCallView.as_view(), name='accept-call'),
    path('reject/', views.RejectCallView.as_view(), name='reject-call'),
    path('active-booking/', views.ActiveBookingView.as_view(), name='active-booking'),
    path('bookings/<int:id>/', views.BookingDetailView.as_view(), name='booking-detail'),
    
    
]

