# urls.py
from django.urls import path, include
from rest_framework_simplejwt.views import TokenRefreshView
from . import views

urlpatterns = [
    # Authentication URLs

    path('auth/token/refresh/', TokenRefreshView.as_view(), name='token-refresh'),
    # Counsellor URLs

    path('api/counsellor/profile/', views.CounsellorProfileView.as_view(), name='counsellor-profile'),
    path('api/counsellor/status/', views.CounsellorStatusView.as_view(), name='counsellor-status'),
    path('api/counsellor/payment-settings/', views.CounsellorPaymentSettingsView.as_view(), name='payment-settings'),
    path('api/call/status/<int:booking_id>/', views.CallStatusView.as_view(), name='call-status'),
    path('api/call/accept/', views.AcceptCallView.as_view(), name='accept-call'),
    path('api/call/reject/', views.RejectCallView.as_view(), name='reject-call'),
    path('api/counsellor/active-booking/', views.ActiveBookingView.as_view(), name='active-booking'),
    path('api/bookings/<int:id>/', views.BookingDetailView.as_view(), name='booking-detail'),
    
    
]

