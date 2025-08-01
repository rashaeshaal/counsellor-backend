# urls.py
from django.urls import path, include
from rest_framework_simplejwt.views import TokenRefreshView
from . import views

urlpatterns = [
    path('counsellors/', views.CounsellorListView.as_view(), name='counsellor-list'),
    path('payment/create-order/', views.CreateOrderView.as_view(), name='create-order'),
    path('payment/verify-payment/', views.VerifyPaymentView.as_view(), name='verify-payment'),
    path('call/initiate/', views.InitiateCallView.as_view(), name='initiate-call'),
    path('wallet/', views.WalletView.as_view(), name='wallet'),
    
]