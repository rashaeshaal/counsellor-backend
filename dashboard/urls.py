# urls.py
from django.urls import path, include
from rest_framework_simplejwt.views import TokenRefreshView
from . import views

urlpatterns = [
    path('api/counsellors/', views.CounsellorListView.as_view(), name='counsellor-list'),
    path('api/payment/create-order/', views.CreateOrderView.as_view(), name='create-order'),
    path('api/payment/verify-payment/', views.VerifyPaymentView.as_view(), name='verify-payment'),
    path('counsellor/list/', views.CounsellorListView.as_view(), name='counsellor-list'),
    path('api/call/initiate/', views.InitiateCallView.as_view(), name='initiate-call'),
    path('wallet/', views.WalletView.as_view(), name='wallet'),
    
]