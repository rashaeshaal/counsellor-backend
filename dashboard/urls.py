# urls.py
from django.urls import path, include
from rest_framework_simplejwt.views import TokenRefreshView
from . import views
from .views import WalletExtraMinutesView

urlpatterns = [
    path('counsellors/', views.CounsellorListView.as_view(), name='counsellor-list'),
    path('payment/create-order/', views.CreateOrderView.as_view(), name='create_order'),
    path('payment/verify-payment/', views.VerifyPaymentView.as_view(), name='verify-payment'),
    path('call/initiate/', views.InitiateCallView.as_view(), name='initiate-call'),
    path('wallet/', views.WalletView.as_view(), name='wallet'),
    path('wallet/extra_minutes/', WalletExtraMinutesView.as_view(), name='wallet-extra-minutes'),
    path('problems/', views.ProblemListView.as_view(), name='problem-list'),
    path('user-problems/', views.UserProblemView.as_view(), name='user-problem'),
    path('profile/', views.UserProfileEditView.as_view(), name='user-profile-edit'),
    path('counsellors/<int:user_id>/', views.CounsellorDetailView.as_view(), name='counsellor-detail'),
    path('call/end/', views.EndCallView.as_view(), name='end-call'),
    path('generate-zego-token/', GenerateZegoTokenView.as_view(), name='generate-zego-token'),
    path('call-status/', CallStatusView.as_view(), name='call-status'),
    path('call-status/<int:booking_id>/', CallStatusCheckView.as_view(), name='call-status-check'),
    path('initiate-call-notification/', InitiateCallNotificationView.as_view(), name='initiate-call-notification'),
    path('end-call-session/', EndCallSessionView.as_view(), name='end-call-session'),
    path('active-booking/', ActiveBookingView.as_view(), name='counsellor-active-booking'),
]