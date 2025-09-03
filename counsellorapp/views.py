from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from dashboard.models import Booking
from .serializers import UpcomingSessionSerializer, RecentActivitySerializer, CounsellorPaymentSerializer
from django.utils import timezone
from userdetails.models import UserProfile
from userdetails.serializers import UserProfileSerializer
from rest_framework_simplejwt.authentication import JWTAuthentication
from django.shortcuts import render
# views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import get_user_model
from rest_framework import status
from itertools import chain
from .models import CounsellorPayment
from django.utils import timezone
from django.conf import settings
import firebase_admin
from firebase_admin import credentials, auth
import logging
from django.views.decorators.csrf import csrf_exempt
import razorpay
import hmac
import hashlib
from dashboard.models import Booking, CallRequest
from userdetails.models import User, UserProfile, OTPAttempt
from .serializers import CounsellorPaymentSerializer
from .models import CounsellorPayment
from userdetails.models import UserProfile
from userdetails.serializers import UserProfileSerializer
from userdetails.serializers import FirebaseAuthSerializer, UserProfileSerializer, UserSerializer
from dashboard.serializers import BookingSerializer
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from userdetails.auth_backends import FirebaseAuthentication



logger = logging.getLogger(__name__)


class UpcomingSessionsView(APIView):
    permission_classes = [IsAuthenticated]


    def get(self, request):
        try:
            counsellor = request.user.userprofile.counsellor
        except AttributeError:
            return Response({"detail": "Counsellor profile not found for the current user."}, status=404)

        now = timezone.now()
        upcoming_sessions = Booking.objects.filter(
            counsellor=counsellor,
            scheduled_at__gte=now,
            status='scheduled'
        ).order_by('scheduled_at')
        
        serializer = UpcomingSessionSerializer(upcoming_sessions, many=True)
        return Response(serializer.data)


class RecentActivityView(APIView):
    
    permission_classes = [IsAuthenticated]
 

    def get(self, request):
        try:
            counsellor = request.user.userprofile.counsellor
        except AttributeError:
            return Response({"detail": "Counsellor profile not found for the current user."}, status=404)

        completed_calls = Booking.objects.filter(counsellor=counsellor, status='completed').order_by('-updated_at')[:10]
        new_bookings = Booking.objects.filter(counsellor=counsellor, status='scheduled').order_by('-created_at')[:10]

        activities = []
        for call in completed_calls:
            activities.append({
                'activity_id': call.id,
                'type': 'Completed Call',
                'description': f"Completed a {call.session_duration}-minute call with {call.user.user.get_full_name() or call.user.user.username}.",
                'timestamp': call.updated_at
            })

        for booking in new_bookings:
            activities.append({
                'activity_id': booking.id,
                'type': 'New Call',
                'description': f"New {booking.session_duration}-minute session call by {booking.user.user.get_full_name() or booking.user.user.username}.",
                'timestamp': booking.created_at
            })

        # Sort activities by timestamp
        activities.sort(key=lambda x: x['timestamp'], reverse=True)
        
        # Limit to recent 20 activities
        activities = activities[:20]

        serializer = RecentActivitySerializer(activities, many=True)
        return Response(serializer.data)


class CounsellorProfileView(APIView):
    permission_classes = [IsAuthenticated]
   

    def get(self, request):
        try:
           
            user_profile = request.user.userprofile
        except UserProfile.DoesNotExist:
            return Response({"detail": "User profile not found."}, status=status.HTTP_404_NOT_FOUND)

        if user_profile.user_role != 'counsellor':
            return Response({"detail": "Access denied. Only counsellors can view this profile."}, status=status.HTTP_403_FORBIDDEN)

        serializer = UserProfileSerializer(user_profile)
        return Response({"counsellor": serializer.data})

    def put(self, request):
        try:
            user_profile = request.user.userprofile
        except UserProfile.DoesNotExist:
            return Response({"detail": "User profile not found."}, status=status.HTTP_404_NOT_FOUND)

        if user_profile.user_role != 'counsellor':
            return Response({"detail": "Access denied. Only counsellors can update this profile."}, status=status.HTTP_403_FORBIDDEN)
        
        # Ensure profile_photo is handled correctly for multipart/form-data
        # request.data will already contain parsed data for both fields and files
        serializer = UserProfileSerializer(user_profile, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({"counsellor": serializer.data})
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class CounsellorPaymentSettingsView(APIView):
    permission_classes = [IsAuthenticated]
  

    def get(self, request, user_id):
        try:
            user_profile = UserProfile.objects.get(id=user_id)
        except UserProfile.DoesNotExist:
            return Response({"detail": "User profile not found."}, status=status.HTTP_404_NOT_FOUND)

        if user_profile.user_role != 'counsellor':
            return Response({"detail": "Access denied. User is not a counsellor."}, status=status.HTTP_403_FORBIDDEN)

        try:
            payment_settings = CounsellorPayment.objects.get(counsellor=user_profile)
        except CounsellorPayment.DoesNotExist:
            return Response({"detail": "Counsellor payment settings not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = CounsellorPaymentSerializer(payment_settings)
        return Response(serializer.data)
    
class CounsellorStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            counsellor = UserProfile.objects.get(user=request.user)
            counsellor.is_active = not counsellor.is_active
            counsellor.save()
            return Response({'is_active': counsellor.is_active})
        except UserProfile.DoesNotExist:
            return Response({'error': 'Counsellor profile not found'}, status=status.HTTP_404_NOT_FOUND)  
        
        

class CounsellorPaymentDetailView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, user_id):
        try:
            payment_settings = CounsellorPayment.objects.get(
                counsellor__user__id=user_id,
                counsellor__user_role='counsellor'
            )
            serializer = CounsellorPaymentSerializer(payment_settings)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except CounsellorPayment.DoesNotExist:
            return Response({'error': 'Payment settings not found'}, status=status.HTTP_404_NOT_FOUND)
                      
                      
                      
class ActiveBookingView(APIView):
    """Get active booking for counsellor"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        try:
            # Get counsellor profile
            user_profile = getattr(request.user, 'profile', None)
            if not user_profile or user_profile.user_role != 'counsellor':
                return Response(
                    {'error': 'User is not a counsellor'},
                    status=status.HTTP_403_FORBIDDEN
                )

            # Get active call request
            active_call = CallRequest.objects.filter(
                counsellor=user_profile,
                status__in=['PENDING', 'ACCEPTED']
            ).select_related('booking', 'user').first()

            if not active_call:
                return Response(
                    {'message': 'No active bookings found'},
                    status=status.HTTP_204_NO_CONTENT
                )

            return Response({
                'booking_id': active_call.booking.id,
                'call_request_id': active_call.id,
                'user_name': active_call.user.get_full_name() or active_call.user.username,
                'user_phone': getattr(active_call.user, 'phone_number', ''),
                'status': active_call.status,
                'requested_at': active_call.requested_at.isoformat(),
                'session_duration': active_call.booking.session_duration,
                'amount': str(active_call.booking.amount)
            })

        except Exception as e:
            logger.error(f"Error getting active booking: {str(e)}")
            return Response(
                {'error': 'Failed to get active booking'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


                      