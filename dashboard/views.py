from django.shortcuts import render
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
# Create your views here.
class CounsellorListView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        logger.debug("CounsellorListView accessed")
        counsellors = UserProfile.objects.filter(user_role='counsellor', is_active=True)
        serializer = UserProfileSerializer(counsellors, many=True)
        logger.debug(f"Returning {len(serializer.data)} counsellors")
        return Response(serializer.data, status=status.HTTP_200_OK)



class CreateOrderView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            counsellor_id = request.data.get('counsellor_id')
            if not counsellor_id:
                return Response({'error': 'Counsellor ID is required'}, status=status.HTTP_400_BAD_REQUEST)
            
            counsellor = UserProfile.objects.get(id=counsellor_id)
            if not counsellor.is_approved or not counsellor.is_active:
                return Response({'error': 'Counsellor is not approved or active'}, status=status.HTTP_400_BAD_REQUEST)
            
            try:
                session_fee = counsellor.payment_settings.session_fee
            except UserProfile.payment_settings.RelatedObjectDoesNotExist:
                return Response({'error': 'Counsellor payment settings not configured'}, status=status.HTTP_400_BAD_REQUEST)
            
            client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
            order_data = {
                'amount': int(session_fee * 100),
                'currency': 'INR',
                'receipt': f'booking_{counsellor_id}_{request.user.id}',
                'payment_capture': 1
            }
            order = client.order.create(data=order_data)
            
            booking = Booking.objects.create(
                user=request.user,
                counsellor=counsellor,
                order_id=order['id'],
                amount=order['amount'] / 100,
                status='pending'
            )
            
            return Response({
                'order_id': order['id'],
                'amount': order['amount'],
                'currency': order['currency'],
                'key': settings.RAZORPAY_KEY_ID,
                'name': 'Counsellor Booking',
                'description': f'Booking with {counsellor.name} for {counsellor.payment_settings.session_duration} minutes',
                'image': 'https://yourapp.com/logo.png',
                'booking_id': booking.id,
                'counsellor': UserProfileSerializer(counsellor).data
            }, status=status.HTTP_201_CREATED)
        
        except UserProfile.DoesNotExist:
            return Response({'error': 'Counsellor not found'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Create order error: {str(e)}")
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# dashboard/views.py
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

            # Verify Razorpay signature
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

            # Update booking status and credit wallet
            try:
                with transaction.atomic():
                    booking = Booking.objects.get(order_id=razorpay_order_id)
                    booking.razorpay_payment_id = razorpay_payment_id
                    booking.status = 'wallet_credited'  # New status to indicate funds in wallet
                    booking.save()

                    # Credit user's wallet
                    wallet, created = Wallet.objects.get_or_create(user=booking.user)
                    wallet.balance = Decimal(wallet.balance) + booking.amount
                    wallet.save()

                    # Log wallet transaction
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
                            'status': 'Payment credited to wallet',
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
        if not booking_id:
            logger.error("No booking_id provided in end call request")
            return Response({'error': 'Booking ID is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            booking = Booking.objects.get(id=booking_id)
            if booking.status != 'wallet_credited':
                logger.error(f"Booking {booking_id} is not in wallet_credited state")
                return Response({'error': 'Invalid booking state'}, status=status.HTTP_400_BAD_REQUEST)

            # Get user and counsellor wallets
            user_wallet = Wallet.objects.get(user=booking.user)
            counsellor_wallet, created = Wallet.objects.get_or_create(user=booking.counsellor.user)

            if user_wallet.balance < booking.amount:
                logger.error(f"Insufficient balance in user wallet for booking {booking_id}")
                return Response({'error': 'Insufficient wallet balance'}, status=status.HTTP_400_BAD_REQUEST)

            # Transfer funds
            user_wallet.balance -= booking.amount
            counsellor_wallet.balance += booking.amount
            user_wallet.save()
            counsellor_wallet.save()

            # Log transactions
            WalletTransaction.objects.create(
                wallet=user_wallet,
                amount=booking.amount,
                transaction_type='TRANSFER',
                description=f"Transfer to counsellor for booking {booking.id}",
                related_booking=booking
            )
            WalletTransaction.objects.create(
                wallet=counsellor_wallet,
                amount=booking.amount,
                transaction_type='DEPOSIT',
                description=f"Received from user for booking {booking.id}",
                related_booking=booking
            )

            # Update booking status
            booking.status = 'completed'
            booking.save()

            # Update CallRequest status
            call_request = CallRequest.objects.filter(booking=booking).first()
            if call_request:
                call_request.status = 'COMPLETED'
                call_request.updated_at = timezone.now()
                call_request.save()

            logger.info(f"Call ended and funds transferred for booking {booking_id}")
            return Response({
                'status': 'Call ended and funds transferred',
                'booking_id': booking.id,
                'user_wallet_balance': user_wallet.balance,
                'counsellor_wallet_balance': counsellor_wallet.balance
            }, status=status.HTTP_200_OK)

        except Booking.DoesNotExist:
            logger.error(f"Booking {booking_id} not found")
            return Response({'error': 'Booking not found'}, status=status.HTTP_404_NOT_FOUND)
        except Wallet.DoesNotExist:
            logger.error(f"Wallet not found for booking {booking_id}")
            return Response({'error': 'Wallet not found'}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Error ending call for booking {booking_id}: {str(e)}")
            return Response({'error': 'Failed to end call and transfer funds'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)  
        
        
        
        
        
        
        
        
        
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
        """List problems selected by the authenticated user."""
        user_problems = UserProblem.objects.filter(user_profile=request.user.userprofile)
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