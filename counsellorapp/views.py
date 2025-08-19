from django.shortcuts import render
# views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import get_user_model
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



logger = logging.getLogger(__name__)
# Create your views here.


class CounsellorPaymentSettingsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            payment_settings = CounsellorPayment.objects.get(counsellor__user=request.user)
            serializer = CounsellorPaymentSerializer(payment_settings)
            return Response(serializer.data)
        except CounsellorPayment.DoesNotExist:
            return Response({'session_fee': 50.00, 'session_duration': 20})

    def post(self, request):
        try:
            payment_settings = CounsellorPayment.objects.get(counsellor__user=request.user)
            serializer = CounsellorPaymentSerializer(payment_settings, data=request.data)
        except CounsellorPayment.DoesNotExist:
            serializer = CounsellorPaymentSerializer(data=request.data)
        if serializer.is_valid():
        
            counsellor = UserProfile.objects.get(user=request.user)
            serializer.save(counsellor=counsellor)
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

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


class CounsellorProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            counsellor = UserProfile.objects.get(user=request.user)
            serializer = UserProfileSerializer(counsellor)
            return Response({
                'user': {'phone_number': counsellor.phone_number, 'name': counsellor.name},
                'counsellor': serializer.data
            })
        except UserProfile.DoesNotExist:
            return Response({'error': 'Counsellor profile not found'}, status=status.HTTP_404_NOT_FOUND)

    def put(self, request):
        try:
            counsellor = UserProfile.objects.get(user=request.user)
            serializer = UserProfileSerializer(counsellor, data=request.data, partial=True)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except UserProfile.DoesNotExist:
            return Response({'error': 'Counsellor profile not found'}, status=status.HTTP_404_NOT_FOUND)



class CallStatusView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request, booking_id):
        try:
            # Check if user is counsellor for this booking
            if hasattr(request.user, 'profile') and request.user.profile.user_role == 'counsellor':
                call_request = CallRequest.objects.filter(
                    booking_id=booking_id,
                    counsellor=request.user.profile
                ).order_by('-created_at').first()
            else:
                # For regular users, check their own bookings
                call_request = CallRequest.objects.filter(
                    booking_id=booking_id,
                    user=request.user
                ).order_by('-created_at').first()
            
            if call_request:
                user = call_request.booking.user
                user_full_name = user.get_full_name().strip()
                username = user.username
                
                # Handle the case where username is literally 'None'
                if username == 'None':
                    username = None
                
                user_name = user_full_name or username or f"User {user.id}"
                
                return Response({
                    'status': call_request.status.lower(),
                    'user_name': user_name,
                    'booking_id': booking_id
                }, status=status.HTTP_200_OK)
            else:
                logger.info(f"No call request found for booking {booking_id}")
                return Response({
                    'status': 'none',
                    'booking_id': booking_id
                }, status=status.HTTP_200_OK)
                
        except Exception as e:
            logger.error(f"Error checking call status for booking {booking_id}: {e}")
            return Response(
                {'error': 'Failed to check call status'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class AcceptCallView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
       
       
        booking_id = request.data.get('booking_id')
        
        if not booking_id:
            logger.error("No booking_id provided in request")
            return Response(
                {'error': 'booking_id is required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # Verify booking exists
            booking = Booking.objects.get(id=booking_id, counsellor=request.user.profile)
            
            # Get the pending call request
            call_request = CallRequest.objects.filter(
                booking_id=booking_id,
                counsellor=booking.counsellor,
                status__in=['PENDING', 'WAITING']
            ).order_by('-created_at').first()
            
            if not call_request:
                logger.error(f"No pending call request found for booking {booking_id}, counsellor {request.user.id}")
                return Response(
                    {'error': 'No pending call request found'}, 
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Update call request status
            call_request.status = 'ACCEPTED'
            call_request.accepted_at = timezone.now()
            call_request.save()
            
            logger.info(f"Call accepted for booking {booking_id} by counsellor {request.user.id}")
            
            # Get counsellor name for notification
            counsellor_full_name = request.user.get_full_name().strip()
            counsellor_name = counsellor_full_name or request.user.username or f"Counsellor {request.user.id}"
            
            # Notify user via WebSocket
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                f'call_{booking_id}',
                {
                    'type': 'call_notification',
                    'message': {
                        'type': 'call_accepted',
                        'booking_id': str(booking_id),
                        'counsellor_name': counsellor_name,
                        'counsellor_id': request.user.id,
                        'timestamp': int(timezone.now().timestamp())
                    }
                }
            )
            
            return Response({
                'message': 'Call accepted successfully',
                'booking_id': booking_id,
                'status': 'accepted'
            }, status=status.HTTP_200_OK)
            
        except Booking.DoesNotExist:
            logger.error(f"Booking {booking_id} not found for counsellor {request.user.id}")
            return Response(
                {'error': 'Booking not found'}, 
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error accepting call for booking {booking_id}: {e}")
            return Response(
                {'error': 'Failed to accept call'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
            
            
            
            
class ActiveBookingView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            if not hasattr(request.user, 'profile') or request.user.profile.user_role != 'counsellor':
                logger.error(f"User {request.user.id} is not a counsellor or has no profile")
                return Response(
                    {'error': 'User is not a counsellor or has no profile'},
                    status=status.HTTP_403_FORBIDDEN
                )

            # Look for bookings with pending call requests first
            pending_call = CallRequest.objects.filter(
                counsellor=request.user.profile,
                status='PENDING'
            ).order_by('-created_at').first()

            if pending_call:
                booking = pending_call.booking
                user_full_name = booking.user.get_full_name().strip()
                user_name = user_full_name or booking.user.username or f"User {booking.user.id}"
                
                logger.info(f"Found pending call for booking {booking.id}")
                return Response({
                    'booking_id': booking.id,
                    'user_name': user_name,
                    'has_pending_call': True
                }, status=status.HTTP_200_OK)

            # Otherwise, look for the most recent completed booking
            booking = Booking.objects.filter(
                counsellor=request.user.profile,
                status='completed'
            ).order_by('-created_at').first()

            if booking:
                user_full_name = booking.user.get_full_name().strip()
                user_name = user_full_name or booking.user.username or f"User {booking.user.id}"
                
                logger.info(f"Found active booking {booking.id} for counsellor {request.user.id}")
                return Response({
                    'booking_id': booking.id,
                    'user_name': user_name,
                    'has_pending_call': False
                }, status=status.HTTP_200_OK)
            else:
                logger.info(f"No active bookings found for counsellor {request.user.id}")
                return Response({
                    'booking_id': None,
                    'message': 'No active bookings found',
                    'has_pending_call': False
                }, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error fetching active booking for counsellor {request.user.id}: {e}")
            return Response(
                {'error': 'Failed to fetch active booking'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class RejectCallView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        booking_id = request.data.get('booking_id')
        
        if not booking_id:
            return Response(
                {'error': 'booking_id is required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # Get the pending call request
            call_request = CallRequest.objects.filter(
                booking_id=booking_id,
                counsellor=request.user.profile,
                status='PENDING'
            ).order_by('-created_at').first()
            
            if call_request:
                call_request.status = 'REJECTED'
                call_request.save()
                
                logger.info(f"Call rejected for booking {booking_id} by counsellor {request.user.id}")
                
                # Notify user via WebSocket
                channel_layer = get_channel_layer()
                async_to_sync(channel_layer.group_send)(
                    f'call_{booking_id}',
                    {
                        'type': 'call_notification',
                        'message': {
                            'type': 'call_rejected',
                            'booking_id': str(booking_id),
                            'timestamp': int(timezone.now().timestamp())
                        }
                    }
                )
            
            return Response({
                'message': 'Call rejected successfully',
                'booking_id': booking_id
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error rejecting call for booking {booking_id}: {e}")
            return Response(
                {'error': 'Failed to reject call'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
            
            
# views.py
class BookingDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, id):
        try:
            
            
            booking = Booking.objects.get(id=id, counsellor=request.user.profile)
            serializer = BookingSerializer(booking)
            return Response(serializer.data)
        except Booking.DoesNotExist:
            logger.error(f"Booking {id} not found for user {request.user.id}")
            return Response({'error': 'Booking not found'}, status=status.HTTP_404_NOT_FOUND) 
        
      