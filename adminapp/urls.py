# urls.py
from django.urls import path
from .views import (
    AdminLoginView, 
    AdminCreateView, 
    NormalUserListView,
    CounsellorUserListView,
    BookingPaymentDetailsAPIView,
    PayoutAPIView,
    CallRequestDetailsAPIView,
    CounsellorPaymentSettingsAPIView,
    ProblemAPIView,
    UserProblemAPIView
    
   
    
    
)

urlpatterns = [
    path('admin-login/', AdminLoginView.as_view(), name='admin-login'),
    path('create-admin/', AdminCreateView.as_view(), name='admin-create'),
    path('users/normal/', NormalUserListView.as_view(), name='normal-user-list'),
    path('users/normal/<int:user_id>/', NormalUserListView.as_view(), name='normal-user-detail'),
    path('users/counsellors/', CounsellorUserListView.as_view(), name='counsellor-list'),

    path('users/counsellors/<int:user_id>/', CounsellorUserListView.as_view(), name='counsellor-detail'),
    path('booking-payment-details/', BookingPaymentDetailsAPIView.as_view(), name='booking-payment-details'),
    path('call-request-details/', CallRequestDetailsAPIView.as_view(), name='call-request-details'),
    path('payout/', PayoutAPIView.as_view(), name='payout'),
    path('payment-settings/', CounsellorPaymentSettingsAPIView.as_view(), name='payment-settings-list'),
    path('payment-settings/<int:user_id>/', CounsellorPaymentSettingsAPIView.as_view(), name='payment-settings-detail'),
    path('problems/', ProblemAPIView.as_view(), name='problem-list'),
    path('problems/<int:pk>/', ProblemAPIView.as_view(), name='problem-detail'),
    path('user-problems/', UserProblemAPIView.as_view(), name='user-problem'),
  
]


