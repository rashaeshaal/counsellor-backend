from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser
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
import datetime
import hmac
import hashlib
from .models import Booking, CallRequest
from userdetails.models import User, UserProfile, OTPAttempt, Wallet, WalletTransaction
from userdetails.serializers import UserProfileSerializer, UserSerializer
import logging
logger = logging.getLogger(__name__)
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
import time
from django.db import transaction
from .serializers import BookingSerializer, CallRequestSerializer,WalletSerializer, WalletTransactionSerializer
from userdetails.models import Wallet, WalletTransaction
from decimal import Decimal
from adminapp.models import UserProblem, Problem
from adminapp.serializers import UserProblemSerializer, ProblemSerializer
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
import json
from .zego_token_generator import generate_token
import time
import jwt
from datetime import datetime, timedelta
# Create your views here.
class CounsellorListView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        logger.debug("CounsellorListView accessed")
        counsellors = UserProfile.objects.filter(user_role='counsellor', is_active=True)
        serializer = UserProfileSerializer(counsellors, many=True)
        logger.debug(f"Returning {len(serializer.data)} counsellors")
        return Response(serializer.data, status=status.HTTP_200_OK)
    def put(self, request, pk):
        logger.debug(f"CounsellorListView PUT request for counsellor ID: {pk}")
        
        # Override permission for PUT to require authentication
        self.permission_classes = [IsAuthenticated]
        self.check_permissions(request)

        try:
            counsellor = UserProfile.objects.get(pk=pk, user_role='counsellor')
        except UserProfile.DoesNotExist:
            logger.error(f"Counsellor with ID {pk} not found")
            return Response({"detail": "Counsellor not found"}, status=status.HTTP_404_NOT_FOUND)

        # Check if the requesting user is the counsellor or an admin
        if request.user != counsellor.user and not request.user.is_staff:
            logger.warning(f"Unauthorized update attempt by user {request.user.id} on counsellor {pk}")
            return Response({"detail": "You do not have permission to edit this profile"}, status=status.HTTP_403_FORBIDDEN)

        serializer = UserProfileSerializer(counsellor, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            logger.debug(f"Counsellor ID {pk} updated successfully")
            return Response(serializer.data, status=status.HTTP_200_OK)
        else:
            logger.error(f"Validation errors for counsellor ID {pk}: {serializer.errors}")
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)



class CreateOrderView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            counsellor_id = request.data.get('counsellor_id')
            if not counsellor_id:
                return Response({'error': 'Counsellor ID is required'}, status=status.HTTP_400_BAD_REQUEST)
            
            # Validate counsellor
            try:
                            counsellor = UserProfile.objects.get(user__id=counsellor_id, user_role='counsellor', is_active=True)
            except UserProfile.DoesNotExist:
                return Response({'error': 'Counsellor not found'}, status=status.HTTP_404_NOT_FOUND)
            
            # Validate counsellor's payment settings
            try:
                session_fee = counsellor.payment_settings.session_fee
                session_duration = counsellor.payment_settings.session_duration
            except UserProfile.payment_settings.RelatedObjectDoesNotExist:
                return Response({'error': 'Counsellor payment settings not configured'}, status=status.HTTP_400_BAD_REQUEST)
            
            # Dynamically select a superuser
            try:
                superuser = UserProfile.objects.filter(
                    user_role='admin',
                    is_approved=True,
                    is_active=True
                ).first()
                if not superuser:
                    return Response({'error': 'No active superuser available for payment'}, status=status.HTTP_404_NOT_FOUND)
            except UserProfile.DoesNotExist:
                return Response({'error': 'No active superuser available for payment'}, status=status.HTTP_404_NOT_FOUND)
            
            client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
            order_data = {
                'amount': int(session_fee * 100),  # Use counsellor's session_fee
                'currency': 'INR',
                'receipt': f'booking_{counsellor_id}_{request.user.id}_superuser_{superuser.id}',
                'payment_capture': 1
            }
            order = client.order.create(data=order_data)
            
            booking = Booking.objects.create(
                user=request.user,
                counsellor=counsellor,  # Booking is for the counsellor
                order_id=order['id'],
                amount=order['amount'] / 100,
                status='pending',
                session_duration=session_duration
            )
            
            return Response({
                'order_id': order['id'],
                'amount': order['amount'],
                'currency': order['currency'],
                'key': settings.RAZORPAY_KEY_ID,
                'name': 'Counsellor Payment',
                'description': f'Payment for booking with {counsellor.name} to superuser {superuser.name}',
                'image': 'https://yourapp.com/logo.png',
                'booking_id': booking.id,
                'counsellor': UserProfileSerializer(counsellor).data,
                'superuser_id': superuser.id  # Include superuser ID for reference
            }, status=status.HTTP_201_CREATED)
        
        except Exception as e:
            logger.error(f"Create order error: {str(e)}")
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class VerifyPaymentView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        try:
            razorpay_payment_id = request.POST.get('razorpay_payment_id')
            razorpay_order_id = request.POST.get('razorpay_order_id')
            razorpay_signature = request.POST.get('razorpay_signature')

            if not all([razorpay_payment_id, razorpay_order_id, razorpay_signature]):
                logger.error("Missing payment verification parameters")
                return Response(
                    {'error': 'Missing required payment parameters'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
            params_dict = {
                'razorpay_payment_id': razorpay_payment_id,
                'razorpay_order_id': razorpay_order_id,
            }
            generated_signature = hmac.new(
                key=settings.RAZORPAY_KEY_SECRET.encode('utf-8'),
                msg=f"{razorpay_order_id}|{razorpay_payment_id}".encode('utf-8'),
                digestmod=hashlib.sha256
            ).hexdigest()

            if generated_signature != razorpay_signature:
                logger.error("Invalid Razorpay signature")
                return Response(
                    {'error': 'Invalid payment signature'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            try:
                with transaction.atomic():
                    booking = Booking.objects.get(order_id=razorpay_order_id)
                    booking.razorpay_payment_id = razorpay_payment_id
                    booking.status = 'wallet_credited'
                    booking.save()

                    wallet, created = Wallet.objects.get_or_create(user=booking.user)
                    wallet.balance = Decimal(wallet.balance) + booking.amount
                    wallet.save()

                    WalletTransaction.objects.create(
                        wallet=wallet,
                        amount=booking.amount,
                        transaction_type='DEPOSIT',
                        description=f"Payment for booking {booking.id}",
                        related_booking=booking
                    )

                    logger.info(f"Payment credited to wallet for booking {booking.id}, order_id: {razorpay_order_id}")
                    return Response(
                        {
                            'booking_id': booking.id,
                            'status': 'Payment Successful',
                            'wallet_balance': wallet.balance
                        },
                        status=status.HTTP_200_OK
                    )
            except Booking.DoesNotExist:
                logger.error(f"Booking not found for order_id: {razorpay_order_id}")
                return Response(
                    {'error': 'Booking not found'},
                    status=status.HTTP_404_NOT_FOUND
                )

        except Exception as e:
            logger.error(f"Payment verification error: {str(e)}")
            return Response(
                {'error': 'Payment verification failed'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )





# dashboard/views.py
class InitiateCallView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        booking_id = request.data.get('booking_id')
        if not booking_id:
            logger.error("No booking_id provided in initiate call request")
            return Response({'error': 'Booking ID is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            booking = Booking.objects.get(id=booking_id, user=request.user)
        except Booking.DoesNotExist:
            logger.error(f"Booking {booking_id} not found for user {request.user.id}")
            return Response({'error': 'Booking not found'}, status=status.HTTP_404_NOT_FOUND)

        try:
            logger.debug(f"Attempting to create CallRequest for booking {booking_id}, user {request.user.id}")
            
            # Get current timestamp
            now = timezone.now()
            
            # Check if CallRequest already exists for this booking
            existing_call = CallRequest.objects.filter(booking=booking).first()
            if existing_call:
                logger.info(f"CallRequest already exists for booking {booking_id}")
                serializer = CallRequestSerializer(existing_call)
                return Response({
                    'status': 'Call already initiated',
                    'call_request': serializer.data
                }, status=status.HTTP_200_OK)
            
            # Create CallRequest with explicit field values
            call_request_data = {
                'booking': booking,
                'user': request.user,
                'counsellor': booking.counsellor,
                'status': 'PENDING',
                'scheduled_at': booking.scheduled_at or now,
                'requested_at': now,  # Explicitly set this
                'created_at': now,    # Explicitly set this too
                'updated_at': now,    # Fix for updated_at field
            }
            
            call_request = CallRequest(**call_request_data)
            
            # Save with error handling
            try:
                call_request.save()
                logger.info(f"CallRequest saved successfully: ID {call_request.id}")
            except Exception as save_error:
                logger.error(f"Error saving CallRequest: {save_error}")
                # Try alternative approach using objects.create with explicit values
                try:
                    call_request = CallRequest.objects.create(
                        booking=booking,
                        user=request.user,
                        counsellor=booking.counsellor,
                        status='PENDING',
                        scheduled_at=booking.scheduled_at or now,
                        requested_at=now,
                        created_at=now,
                        updated_at=now
                    )
                    logger.info(f"CallRequest created via objects.create: ID {call_request.id}")
                except Exception as create_error:
                    logger.error(f"Error with objects.create: {create_error}")
                    # Last resort: use raw SQL
                    from django.db import connection
                    with connection.cursor() as cursor:
                        cursor.execute("""
                            INSERT INTO dashboard_callrequest 
                            (booking_id, user_id, counsellor_id, status, scheduled_at, requested_at, created_at, updated_at)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                            RETURNING id
                        """, [
                            booking.id, 
                            request.user.id, 
                            booking.counsellor.id, 
                            'PENDING', 
                            booking.scheduled_at or now, 
                            now, 
                            now, 
                            now
                        ])
                        call_request_id = cursor.fetchone()[0]
                        call_request = CallRequest.objects.get(id=call_request_id)
                        logger.info(f"CallRequest created via raw SQL: ID {call_request.id}")

            logger.debug(f"CallRequest created: ID {call_request.id}, requested_at {call_request.requested_at}")

            # Send WebSocket notification
            try:
                channel_layer = get_channel_layer()
                async_to_sync(channel_layer.group_send)(
                    f'call_{booking_id}',
                    {
                        'type': 'call_notification',
                        'message': {
                            'type': 'call_initiated',
                            'booking_id': str(booking_id),
                            'user_id': request.user.id,
                            'user_name': request.user.get_full_name() or request.user.username,
                            'timestamp': int(now.timestamp())
                        }
                    }
                )
            except Exception as ws_error:
                logger.warning(f"WebSocket notification failed: {ws_error}")
                # Don't fail the request if WebSocket fails

            logger.info(f"Call initiated for booking {booking_id} by user {request.user.id}")
            serializer = CallRequestSerializer(call_request)
            return Response({
                'status': 'Call initiated',
                'call_request': serializer.data
            }, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error initiating call for booking {booking_id}: {str(e)}")
            logger.error(f"Exception type: {type(e).__name__}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return Response({
                'error': 'Failed to initiate call',
                'detail': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)




class CheckCounsellorAvailabilityView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request, counsellor_id):
        try:
            counsellor = UserProfile.objects.get(id=counsellor_id, user_role='counsellor', is_active=True)
            # Add logic to check availability (e.g., online status)
            return Response({'available': True}, status=status.HTTP_200_OK)
        except UserProfile.DoesNotExist:
            return Response({'error': 'Counsellor not found'}, status=status.HTTP_404_NOT_FOUND)   
        
        
        
# dashboard/views.py
class EndCallView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        booking_id = request.data.get('booking_id')
        actual_duration = request.data.get('actual_duration') # Duration in minutes

        if not booking_id:
            logger.error("No booking_id provided in end call request")
            return Response({'error': 'Booking ID is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        if actual_duration is None:
            logger.error("No actual_duration provided in end call request")
            return Response({'error': 'Actual duration is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            actual_duration = Decimal(str(actual_duration)) # Ensure Decimal type
        except Exception:
            logger.error(f"Invalid actual_duration format: {actual_duration}")
            return Response({'error': 'Invalid actual_duration format'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            booking = Booking.objects.get(id=booking_id)
            if booking.status != 'wallet_credited':
                logger.error(f"Booking {booking_id} is not in wallet_credited state")
                return Response({'error': 'Invalid booking state'}, status=status.HTTP_400_BAD_REQUEST)

            user_wallet = Wallet.objects.get(user=booking.user)
            counsellor_wallet, created = Wallet.objects.get_or_create(user=booking.counsellor.user)

            # Calculate extra minutes for unused time
            session_duration = Decimal(str(booking.session_duration)) # Ensure Decimal type
            
            time_remaining = max(Decimal('0.00'), session_duration - actual_duration)
            extra_minutes_to_credit = int(time_remaining) # Convert to integer minutes

            # Transfer full booking amount to counsellor (as per new requirement)
            amount_to_transfer_to_counsellor = booking.amount

            # Ensure user has enough balance for the full booking amount
            # This check might be redundant if payment is already handled at booking creation
            # but kept for safety.
            if user_wallet.balance < amount_to_transfer_to_counsellor:
                logger.error(f"Insufficient balance in user wallet for booking {booking.id} to cover full amount")
                return Response({'error': 'Insufficient wallet balance to cover full session cost'}, status=status.HTTP_400_BAD_REQUEST)

            # Transfer funds
            user_wallet.balance -= amount_to_transfer_to_counsellor
            counsellor_wallet.balance += amount_to_transfer_to_counsellor
            user_wallet.save()
            counsellor_wallet.save()

            # Log transactions for fund transfer
            WalletTransaction.objects.create(
                wallet=user_wallet,
                amount=amount_to_transfer_to_counsellor,
                transaction_type='TRANSFER',
                description=f"Transfer to counsellor for booking {booking.id} (full session cost)",
                related_booking=booking
            )
            WalletTransaction.objects.create(
                wallet=counsellor_wallet,
                amount=amount_to_transfer_to_counsellor,
                transaction_type='DEPOSIT',
                description=f"Received from user for booking {booking.id} (full session cost)",
                related_booking=booking
            )

            # Credit extra minutes if applicable
            if extra_minutes_to_credit > 0:
                user_wallet.extra_minutes += extra_minutes_to_credit # Add extra minutes to user's wallet
                user_wallet.save()
                WalletTransaction.objects.create(
                    wallet=user_wallet,
                    amount=Decimal(str(extra_minutes_to_credit)), # Store minutes as amount for transaction log
                    transaction_type='EXTRA_MINUTES_CREDIT',
                    description=f"Credited {extra_minutes_to_credit} extra minutes for unused session time for booking {booking.id}",
                    related_booking=booking
                )
                logger.info(f"Credited {extra_minutes_to_credit} extra minutes to user {booking.user.id} for booking {booking.id}")

            # Update booking status
            booking.status = 'completed'
            booking.save()

            # Update CallRequest status
            call_request = CallRequest.objects.filter(booking=booking).first()
            if call_request:
                call_request.status = 'COMPLETED'
                call_request.ended_at = timezone.now()
                call_request.save()

            logger.info(f"Call ended, funds transferred, and extra minutes processed for booking {booking_id}")
            return Response({
                'status': 'Call ended, funds transferred, and extra minutes processed',
                'booking_id': booking.id,
                'user_wallet_balance': user_wallet.balance,
                'counsellor_wallet_balance': counsellor_wallet.balance,
                'extra_minutes_credited': extra_minutes_to_credit
            }, status=status.HTTP_200_OK)

        except Booking.DoesNotExist:
            logger.error(f"Booking {booking_id} not found")
            return Response({'error': 'Booking not found'}, status=status.HTTP_404_NOT_FOUND)
        except Wallet.DoesNotExist:
            logger.error(f"Wallet not found for booking {booking.id}")
            return Response({'error': 'Wallet not found'}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Error ending call for booking {booking.id}: {str(e)}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return Response({'error': 'Failed to end call and process extra minutes'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)  
        
        
        
        
        
        
        
        
        
class WalletView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            wallet = Wallet.objects.get(user=request.user)
            transactions = WalletTransaction.objects.filter(wallet=wallet).order_by('-created_at')
            
            wallet_serializer = WalletSerializer(wallet)
            transaction_serializer = WalletTransactionSerializer(transactions, many=True)
            
            logger.info(f"Wallet details fetched for user {request.user.id}")
            return Response({
                'wallet': wallet_serializer.data,
                'transactions': transaction_serializer.data
            }, status=status.HTTP_200_OK)
        except Wallet.DoesNotExist:
            logger.warning(f"No wallet found for user {request.user.id}")
            return Response({
                'wallet': {'balance': 0.00},
                'transactions': []
            }, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"Error fetching wallet details for user {request.user.id}: {str(e)}")
            return Response(
                {'error': 'Failed to fetch wallet details'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )                   
            
            
class ProblemListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """List all problems."""
        problems = Problem.objects.all()
        serializer = ProblemSerializer(problems, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

class UserProblemView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        import pdb; pdb.set_trace()
 
        """List problems selected by the authenticated user."""
        user_problems = UserProblem.objects.filter(user_profile=request.user.user_profile)
        serializer = UserProblemSerializer(user_problems, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        """Select a problem for the authenticated user."""
        problem_id = request.data.get('problem_id')

        try:
           
            problem = Problem.objects.get(pk=problem_id)
            user_profile = UserProfile.objects.get(user=request.user)

            if UserProblem.objects.filter(user_profile=user_profile, problem=problem).exists():
                return Response({"error": "Problem already selected"}, status=status.HTTP_400_BAD_REQUEST)

            data = {
                'problem_id': problem.id,
                'user_profile': user_profile.id
            }

            serializer = UserProblemSerializer(data=data)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        except Problem.DoesNotExist:
            return Response({"error": "Problem not found"}, status=status.HTTP_404_NOT_FOUND)
        except UserProfile.DoesNotExist:
            return Response({"error": "User profile not found"}, status=status.HTTP_404_NOT_FOUND)  
        
        
class UserProfileEditView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def get(self, request):
        try:
            # Get the user's profile
            profile = UserProfile.objects.get(user=request.user)
            if profile.user_role != 'normal':
                logger.warning(f"User {request.user.id} attempted to access edit profile but is not a normal user")
                return Response(
                    {'error': 'Only normal users can edit their profile'},
                    status=status.HTTP_403_FORBIDDEN
                )
            serializer = UserProfileSerializer(profile)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except UserProfile.DoesNotExist:
            logger.error(f"UserProfile not found for user {request.user.id}")
            return Response(
                {'error': 'User profile not found'},
                status=status.HTTP_404_NOT_FOUND
            )

    def patch(self, request):
        try:
            # Get the user's profile
            profile = UserProfile.objects.get(user=request.user)
            if profile.user_role != 'normal':
                logger.warning(f"User {request.user.id} attempted to update profile but is not a normal user")
                return Response(
                    {'error': 'Only normal users can edit their profile'},
                    status=status.HTTP_403_FORBIDDEN
                )

            # Update profile with provided data
            serializer = UserProfileSerializer(profile, data=request.data, partial=True)
            if serializer.is_valid():
                # If phone_number is provided, update User.phone_number as well
                phone_number = request.data.get('phone_number')
                if phone_number:
                    request.user.phone_number = phone_number
                    request.user.save()

                # If email is provided, update User.email
                email = request.data.get('email')
                if email:
                    request.user.email = email
                    request.user.save()

                serializer.save()
                logger.info(f"User {request.user.id} updated their profile successfully")
                return Response(serializer.data, status=status.HTTP_200_OK)
            else:
                logger.error(f"Validation errors for user {request.user.id}: {serializer.errors}")
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except UserProfile.DoesNotExist:
            logger.error(f"UserProfile not found for user {request.user.id}")
            return Response(
                {'error': 'User profile not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error updating profile for user {request.user.id}: {str(e)}")
            return Response(
                {'error': 'An error occurred while updating the profile'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
 
 
class CounsellorDetailView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        user_id = self.kwargs['user_id']
        try:
            counsellor = UserProfile.objects.get(user_id=user_id, user_role='counsellor', is_active=True)
            serializer = UserProfileSerializer(counsellor)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except UserProfile.DoesNotExist:
            return Response({"error": "Counsellor not found"}, status=status.HTTP_404_NOT_FOUND)



class WalletExtraMinutesView(APIView):
   
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            wallet = Wallet.objects.get(user=request.user.profile)
            serializer = WalletExtraMinutesSerializer(wallet)
            return Response(serializer.data)
        except Wallet.DoesNotExist:
            return Response({"extra_minutes": 0}, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"Error fetching extra minutes for user {request.user.id}: {str(e)}")
            return Response(
                {'error': 'Failed to fetch extra minutes'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class GenerateZegoTokenView(APIView):
    """Generate Zego token for audio call - API View version"""
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        try:
            user_id = request.data.get('userID')
            room_id = request.data.get('roomID')

            if not user_id or not room_id:
                return Response(
                    {'error': 'userID and roomID are required'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Validate that the user has permission for this room/booking
            try:
                booking_id = int(room_id)
                booking = Booking.objects.get(id=booking_id)
                
                # Check if user is part of this booking
                user_profile = getattr(request.user, 'profile', None)
                if (request.user != booking.user and 
                    user_profile != booking.counsellor):
                    return Response(
                        {'error': 'Permission denied for this booking'}, 
                        status=status.HTTP_403_FORBIDDEN
                    )
                
            except (ValueError, Booking.DoesNotExist):
                return Response(
                    {'error': 'Invalid booking ID'}, 
                    status=status.HTTP_404_NOT_FOUND
                )

            # Get credentials from settings
            app_id = settings.ZEGO_APP_ID
            server_secret = settings.ZEGO_SERVER_SECRET

            # Generate token with extended validity
            token = generate_token(
                app_id, 
                server_secret, 
                user_id, 
                room_id, 
                privilege_expire_in_seconds=3600
            )

            # Log token generation for debugging
            logger.info(f"Generated Zego token for user {user_id} in room {room_id}")

            return Response({
                'kitToken': token,
                'roomID': room_id,
                'userID': user_id,
                'tokenExpiresAt': (timezone.now() + timedelta(hours=1)).isoformat()
            })

        except Exception as e:
            logger.error(f"Error generating Zego token: {str(e)}")
            return Response(
                {'error': 'Failed to generate token'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class CallStatusView(APIView):
    """Handle call status updates and notify relevant parties"""
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        try:
            booking_id = request.data.get('booking_id')
            user_role = request.data.get('user_role')
            action = request.data.get('action')
            timestamp = request.data.get('timestamp')

            if not all([booking_id, user_role, action]):
                return Response(
                    {'error': 'Missing required fields'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Get booking details
            try:
                booking = Booking.objects.get(id=booking_id)
            except Booking.DoesNotExist:
                return Response(
                    {'error': 'Booking not found'}, 
                    status=status.HTTP_404_NOT_FOUND
                )

            # Get or create call request
            call_request, created = CallRequest.objects.get_or_create(
                booking=booking,
                defaults={
                    'counsellor': booking.counsellor,
                    'user': booking.user,
                    'status': 'PENDING'
                }
            )

            # Prepare notification data
            notification_data = {
                'type': 'call_status',
                'booking_id': booking_id,
                'user_role': user_role,
                'action': action,
                'timestamp': timestamp,
                'room_id': str(booking_id)
            }

            # Send real-time notification via WebSocket
            channel_layer = get_channel_layer()
            if channel_layer:
                group_name = f'call_{booking_id}'
                async_to_sync(channel_layer.group_send)(
                    group_name,
                    {
                        'type': 'call_notification',
                        'message': notification_data
                    }
                )

            # Update call request and booking status based on action
            if action == 'joined':
                if user_role == 'user':
                    # User joined the call
                    pass
                elif user_role == 'counsellor':
                    # Counsellor joined the call
                    call_request.status = 'ACCEPTED'
                    call_request.accepted_at = timezone.now()
                    call_request.save()
                
                # Update booking status to completed when call starts
                if booking.status == 'wallet_credited':
                    booking.status = 'completed'
                    booking.save()

            elif action == 'left':
                call_request.status = 'ENDED'
                call_request.ended_at = timezone.now()
                call_request.save()

            return Response({
                'status': 'success',
                'message': 'Call status updated successfully',
                'booking_status': booking.status,
                'call_status': call_request.status
            })

        except Exception as e:
            logger.error(f"Error updating call status: {str(e)}")
            return Response(
                {'error': 'Failed to update call status'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class CallStatusCheckView(APIView):
    """Check the current status of a call"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request, booking_id):
        try:
            booking = Booking.objects.get(id=booking_id)
            
            # Check if user has permission to view this booking
            user_profile = getattr(request.user, 'profile', None)
            if (request.user != booking.user and 
                user_profile != booking.counsellor):
                return Response(
                    {'error': 'Permission denied'}, 
                    status=status.HTTP_403_FORBIDDEN
                )

            # Get call request if exists
            call_request = CallRequest.objects.filter(booking=booking).first()

            response_data = {
                'booking_id': booking.id,
                'booking_status': booking.status,
                'call_status': call_request.status if call_request else 'NOT_CREATED',
                'counsellor_name': booking.counsellor.name or 'Counsellor',
                'session_duration': booking.session_duration,
                'created_at': booking.created_at.isoformat(),
            }

            if call_request:
                response_data.update({
                    'call_request_id': call_request.id,
                    'requested_at': call_request.requested_at.isoformat(),
                    'accepted_at': call_request.accepted_at.isoformat() if call_request.accepted_at else None,
                    'ended_at': call_request.ended_at.isoformat() if call_request.ended_at else None,
                })

            return Response(response_data)

        except Booking.DoesNotExist:
            return Response(
                {'error': 'Booking not found'}, 
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error checking call status: {str(e)}")
            return Response(
                {'error': 'Failed to check call status'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )






class InitiateCallNotificationView(APIView):
    """Send notification to counsellor when user initiates a call"""
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        try:
            booking_id = request.data.get('booking_id')
            
            if not booking_id:
                return Response(
                    {'error': 'booking_id is required'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )

            try:
                booking = Booking.objects.get(id=booking_id)
            except Booking.DoesNotExist:
                return Response(
                    {'error': 'Booking not found'}, 
                    status=status.HTTP_404_NOT_FOUND
                )

            # Check if user owns this booking
            if request.user != booking.user:
                return Response(
                    {'error': 'Permission denied'}, 
                    status=status.HTTP_403_FORBIDDEN
                )

            # Create or get call request
            call_request, created = CallRequest.objects.get_or_create(
                booking=booking,
                defaults={
                    'counsellor': booking.counsellor,
                    'user': booking.user,
                    'status': 'PENDING'
                }
            )

            # Send real-time notification via WebSocket
            channel_layer = get_channel_layer()
            if channel_layer:
                group_name = f'call_{booking_id}'
                notification_data = {
                    'type': 'incoming_call',
                    'booking_id': booking_id,
                    'call_request_id': call_request.id,
                    'user_name': request.user.get_full_name() or request.user.username,
                    'user_phone': getattr(request.user, 'phone_number', ''),
                    'room_id': str(booking_id),
                    'timestamp': timezone.now().isoformat()
                }
                
                async_to_sync(channel_layer.group_send)(
                    group_name,
                    {
                        'type': 'call_notification',
                        'message': notification_data
                    }
                )

            return Response({
                'status': 'success',
                'message': 'Call notification sent to counsellor',
                'call_request_id': call_request.id
            })

        except Exception as e:
            logger.error(f"Error sending call notification: {str(e)}")
            return Response(
                {'error': 'Failed to send notification'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class EndCallSessionView(APIView):
    """Handle call termination and cleanup"""
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        try:
            booking_id = request.data.get('booking_id')
            ended_by = request.data.get('ended_by', 'user')  # 'user' or 'counsellor'
            
            if not booking_id:
                return Response(
                    {'error': 'booking_id is required'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )

            try:
                booking = Booking.objects.get(id=booking_id)
            except Booking.DoesNotExist:
                return Response(
                    {'error': 'Booking not found'}, 
                    status=status.HTTP_404_NOT_FOUND
                )

            # Get call request
            call_request = CallRequest.objects.filter(booking=booking).first()
            if not call_request:
                return Response(
                    {'error': 'Call request not found'}, 
                    status=status.HTTP_404_NOT_FOUND
                )

            # Update call request status
            call_request.status = 'ENDED'
            call_request.ended_at = timezone.now()
            call_request.save()

            # Send notifications via WebSocket
            channel_layer = get_channel_layer()
            if channel_layer:
                group_name = f'call_{booking_id}'
                end_notification = {
                    'type': 'call_ended',
                    'booking_id': booking_id,
                    'call_request_id': call_request.id,
                    'ended_by': ended_by,
                    'timestamp': timezone.now().isoformat()
                }

                async_to_sync(channel_layer.group_send)(
                    group_name,
                    {
                        'type': 'call_notification',
                        'message': end_notification
                    }
                )

            return Response({
                'status': 'success',
                'message': 'Call ended successfully',
                'call_request_id': call_request.id
            })

        except Exception as e:
            logger.error(f"Error ending call: {str(e)}")
            return Response(
                {'error': 'Failed to end call'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


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