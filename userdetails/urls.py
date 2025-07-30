# urls.py
from django.urls import path, include
from rest_framework_simplejwt.views import TokenRefreshView
from . import views

urlpatterns = [
    # Authentication URLs

    path('auth/token/refresh/', TokenRefreshView.as_view(), name='token-refresh'),
    # User URLs
    path('api/auth/counsellor/register/', views.UserProfileRegisterView.as_view(), name='counsellor-register'),
    path('api/auth/counsellorlogin/', views.UserLoginView.as_view(), name='counsellor-login'),
    path('api/auth/firebase-login/', views.FirebaseAuthView.as_view(), name='firebase-auth'),
   
  
]