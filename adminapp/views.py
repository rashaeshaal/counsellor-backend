# views.py
from django.contrib.auth import authenticate
from django.core.exceptions import ValidationError, ObjectDoesNotExist
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from userdetails.models import User, UserProfile
from userdetails.serializers import UserSerializer, UserProfileSerializer
import logging
logger = logging.getLogger(__name__)
from dashboard.models import Booking, CallRequest
from django.db.models import Prefetch
from .models import Payout
import razorpay
from django.db import transaction
from django.conf import settings
import razorpay
from django.db import transaction
from django.conf import settings
from counsellorapp.models import CounsellorPayment
from counsellorapp.serializers import CounsellorPaymentSerializer
from .serializers import ProblemSerializer
from .models import Problem
razorpay_client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
class AdminLoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        phone_number = request.data.get('phone_number', '').strip()
        password = request.data.get('password', '').strip()
        logger.debug(f"Admin login request for phone number: {phone_number}")

        if not phone_number or not password:
            return Response(
                {'error': 'Phone number and password are required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        user = authenticate(request, phone_number=phone_number, password=password)
        if not user:
            logger.error(f"Authentication failed for phone_number: {phone_number}")
            return Response(
                {'error': 'Invalid phone number or password'},
                status=status.HTTP_401_UNAUTHORIZED
            )

        if not user.is_admin or not user.is_staff or not user.is_superuser:
            logger.error(f"User {phone_number} is not an admin")
            return Response(
                {'error': 'User is not an admin'},
                status=status.HTTP_403_FORBIDDEN
            )

        try:
            profile = user.profile
            if profile.user_role != 'admin':
                logger.error(f"User {phone_number} is not registered as an admin")
                return Response(
                    {'error': 'User is not registered as an admin'},
                    status=status.HTTP_403_FORBIDDEN
                )
        except AttributeError:
            logger.error(f"Admin profile not found for {phone_number}")
            return Response(
                {'error': 'Admin profile not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        refresh = RefreshToken.for_user(user)
        logger.info(f"Admin login successful for {phone_number}")
        return Response({
            'refresh': str(refresh),
            'access': str(refresh.access_token),
            'user': UserSerializer(user).data,
            'profile': UserProfileSerializer(profile).data
        }, status=status.HTTP_200_OK)

class AdminCreateView(APIView): 
    permission_classes = [AllowAny]

    def post(self, request):
        logger.debug(f"Admin creation request data: {request.data}")
        required_fields = ['phone_number', 'password', 'name']
        missing_fields = [field for field in required_fields if not request.data.get(field)]
        if missing_fields:
            logger.error(f"Missing fields: {missing_fields}")
            return Response(
                {'error': f'Missing required fields: {", ".join(missing_fields)}'},
                status=status.HTTP_400_BAD_REQUEST
            )

        phone_number = request.data.get('phone_number')
        email = request.data.get('email')
        password = request.data.get('password')
        name = request.data.get('name')

        if User.objects.filter(phone_number=phone_number).exists():
            logger.error(f"User with phone number {phone_number} already exists")
            return Response(
                {'error': 'User with this phone number already exists'},
                status=status.HTTP_400_BAD_REQUEST
            )
        if email and User.objects.filter(email=email).exists():
            logger.error(f"User with email {email} already exists")
            return Response(
                {'error': 'User with this email already exists'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            user = User.objects.create_user(
                phone_number=phone_number,
                email=email,
                password=password,
                is_admin=True,
                is_staff=True,
                is_superuser=True
            )
            logger.info(f"Created new admin user with phone_number {phone_number}")
        except Exception as e:
            logger.error(f"Error creating admin user: {str(e)}")
            return Response(
                {'error': 'Failed to create admin user'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        serializer_data = {
            'phone_number': phone_number,
            'name': name,
            'email': email,
            'user_role': 'admin',
            'is_approved': True,
            'is_active': True
        }

        serializer = UserProfileSerializer(data=serializer_data, context={'user': user})
        if serializer.is_valid():
            profile = serializer.save()
            logger.info(f"Admin profile created for {phone_number}")
            return Response({
                'message': 'Admin created successfully',
                'user': UserSerializer(user).data,
                'profile': UserProfileSerializer(profile).data
            }, status=status.HTTP_201_CREATED)
        logger.error(f"Serializer errors: {serializer.errors}")
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    
    



class NormalUserListView(APIView):
    permission_classes = [IsAuthenticated, IsAdminUser]  # Only authenticated admins can access

    def get(self, request):
        """
        Retrieve list of normal users (non-admins, non-counsellors)
        """
        try:
            # Filter users who are neither admins nor counsellors
            users = User.objects.filter(
                is_admin=False,
                profile__user_role='normal'
            ).select_related('profile')
            
            serializer = UserSerializer(users, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)
        
        except Exception as e:
            return Response(
                {'error': f'Error fetching users: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def delete(self, request, user_id):
        """
        Delete a normal user by ID
        """
        try:
            user = User.objects.get(id=user_id, is_admin=False, profile__user_role='normal')
            user.delete()
            return Response(
                {'message': 'User deleted successfully'},
                status=status.HTTP_204_NO_CONTENT
            )
        except ObjectDoesNotExist:
            return Response(
                {'error': 'User not found or not a normal user'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {'error': f'Error deleting user: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def patch(self, request, user_id):
        """
        Update a normal user's information
        """
        try:
            user = User.objects.get(id=user_id, is_admin=False, profile__user_role='normal')
            profile = user.profile

            # Update User fields
            user_serializer = UserSerializer(user, data=request.data, partial=True)
            if user_serializer.is_valid():
                user_serializer.save()

            # Update UserProfile fields
            profile_serializer = UserProfileSerializer(profile, data=request.data, partial=True)
            if profile_serializer.is_valid():
                profile_serializer.save()
                
                # Ensure phone_number sync
                if 'phone_number' in request.data:
                    profile.phone_number = user.phone_number
                    profile.save()

                return Response(
                    {
                        'user': user_serializer.data,
                        'profile': profile_serializer.data
                    },
                    status=status.HTTP_200_OK
                )
            else:
                return Response(
                    profile_serializer.errors,
                    status=status.HTTP_400_BAD_REQUEST
                )

        except ObjectDoesNotExist:
            return Response(
                {'error': 'User not found or not a normal user'},
                status=status.HTTP_404_NOT_FOUND
            )
        except ValidationError as e:
            return Response(
                {'error': f'Validation error: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            return Response(
                {'error': f'Error updating user: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
            
            
class CounsellorUserListView(APIView):
    permission_classes = [IsAdminUser]  # Only authenticated admins can access

    def get(self, request):
        """
        Retrieve list of counsellor user profiles
        """
        try:
            profiles = UserProfile.objects.filter(
                user_role='counsellor',
                user__is_admin=False
            ).select_related('user')
            
            serializer = UserProfileSerializer(profiles, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)
        
        except Exception as e:
            logger.error(f"Error fetching counsellor profiles: {str(e)}")
            return Response(
                {'error': f'Error fetching counsellor profiles: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def delete(self, request, user_id):
        """
        Delete a counsellor user profile by user ID
        """
        try:
            logger.debug(f"Attempting to delete counsellor with user_id={user_id}")
            profile = UserProfile.objects.get(
                user__id=user_id,
                user_role='counsellor',
                user__is_admin=False
            )
            user = profile.user
            user.delete()  # Deleting the user also deletes the profile due to CASCADE
            logger.info(f"Counsellor user_id={user_id} deleted successfully")
            return Response(
                {'message': 'Counsellor user deleted successfully'},
                status=status.HTTP_204_NO_CONTENT
            )
        except ObjectDoesNotExist:
            logger.warning(f"Counsellor user_id={user_id} not found")
            return Response(
                {'error': 'Counsellor user not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error deleting counsellor user_id={user_id}: {str(e)}")
            return Response(
                {'error': f'Error deleting counsellor user: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def patch(self, request, user_id):
        """
        Update a counsellor user's profile information
        """
        try:
            logger.debug(f"Attempting to update counsellor with user_id={user_id}, data={request.data}")
            profile = UserProfile.objects.get(
                id=user_id,
                user_role='counsellor',
                user__is_admin=False
            )
            user = profile.user

            # Update User fields (only phone_number and email, if provided)
            user_data = {}
            if 'phone_number' in request.data:
                user_data['phone_number'] = request.data['phone_number']
            if 'email' in request.data:
                user_data['email'] = request.data['email']
            
            if user_data:
                user_serializer = UserSerializer(user, data=user_data, partial=True)
                if user_serializer.is_valid():
                    user_serializer.save()
                else:
                    logger.warning(f"User validation failed for user_id={user_id}: {user_serializer.errors}")
                    return Response(
                        user_serializer.errors,
                        status=status.HTTP_400_BAD_REQUEST
                    )

            # Update UserProfile fields
            serializer = UserProfileSerializer(profile, data=request.data, partial=True)
            if serializer.is_valid():
                serializer.save()
                
                # Ensure phone_number sync
                if 'phone_number' in request.data:
                    profile.phone_number = user.phone_number
                    profile.save()

                logger.info(f"Counsellor user_id={user_id} updated successfully")
                return Response(serializer.data, status=status.HTTP_200_OK)
            else:
                logger.warning(f"Profile validation failed for user_id={user_id}: {serializer.errors}")
                return Response(
                    serializer.errors,
                    status=status.HTTP_400_BAD_REQUEST
                )

        except ObjectDoesNotExist:
            logger.warning(f"Counsellor user_id={user_id} not found")
            return Response(
                {'error': 'Counsellor user not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except ValidationError as e:
            logger.warning(f"Validation error for user_id={user_id}: {str(e)}")
            return Response(
                {'error': f'Validation error: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Error updating counsellor user_id={user_id}: {str(e)}")
            return Response(
                {'error': f'Error updating counsellor user: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )          
            
class BookingPaymentDetailsAPIView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        try:
            # Prefetch related CallRequest objects to optimize query
            bookings = Booking.objects.select_related('user', 'counsellor').prefetch_related(
                Prefetch('callrequest_set', queryset=CallRequest.objects.select_related('user', 'counsellor'))
            ).order_by('-created_at')

            # Serialize booking and payment details
            booking_data = []
            for booking in bookings:
                call_requests = booking.callrequest_set.all()
                booking_data.append({
                    'booking_id': booking.id,
                    'order_id': booking.order_id,
                    'user': {
                        'id': booking.user.id,
                        'username': booking.user.username,
                        'email': booking.user.email
                    },
                    'counsellor': {
                        'id': booking.counsellor.id,
                        'name': booking.counsellor.name
                    },
                    'amount': float(booking.amount),  # Convert Decimal to float for JSON
                    'status': booking.status,
                    'razorpay_payment_id': booking.razorpay_payment_id,
                    'created_at': booking.created_at,
                    'scheduled_at': booking.scheduled_at,
                    'call_requests': [
                        {
                            'id': cr.id,
                            'status': cr.status,
                            'requested_at': cr.requested_at,
                            'updated_at': cr.updated_at,
                            'accepted_at': cr.accepted_at,
                            'ended_at': cr.ended_at,
                            'scheduled_at': cr.scheduled_at
                        } for cr in call_requests
                    ]
                })

            return Response({
                'status': 'success',
                'data': booking_data
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({
                'status': 'error',
                'message': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)            
            
class CallRequestDetailsAPIView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        try:
            # Prefetch related Booking, User, and UserProfile to optimize query
            call_requests = CallRequest.objects.select_related(
                'user', 'counsellor', 'booking__user', 'booking__counsellor'
            ).order_by('-requested_at')

            # Serialize call request details
            call_data = [
                {
                    'id': call_request.id,
                    'user': {
                        'id': call_request.user.id,
                        'username': call_request.user.username,
                        'email': call_request.user.email
                    },
                    'counsellor': {
                        'id': call_request.counsellor.id,
                        'name': call_request.counsellor.name
                    },
                    'booking': {
                        'id': call_request.booking.id,
                        'order_id': call_request.booking.order_id,
                        'amount': float(call_request.booking.amount),  # Convert Decimal to float for JSON
                        'status': call_request.booking.status
                    },
                    'status': call_request.status,
                    'requested_at': call_request.requested_at,
                    'updated_at': call_request.updated_at,
                    'accepted_at': call_request.accepted_at,
                    'ended_at': call_request.ended_at,
                    'scheduled_at': call_request.scheduled_at
                }
                for call_request in call_requests
            ]

            return Response({
                'status': 'success',
                'data': call_data
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({
                'status': 'error',
                'message': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
                        


class PayoutAPIView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request):
        try:
            logger.debug(f"Payout request data: {request.data}")
            
            # Validate required fields
            required_fields = ['counsellor_id', 'amount', 'notes']
            missing_fields = [field for field in required_fields if field not in request.data]
            if missing_fields:
                logger.error(f"Missing required fields: {missing_fields}")
                return Response(
                    {'error': f'Missing required fields: {", ".join(missing_fields)}'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            counsellor_id = request.data['counsellor_id']
            amount = request.data['amount']  # Amount in paise
            notes = request.data['notes']

            # Validate counsellor
            try:
                counsellor_profile = UserProfile.objects.get(
                    user__id=counsellor_id,
                    user_role='counsellor',
                    user__is_admin=False
                )
            except ObjectDoesNotExist:
                logger.warning(f"Counsellor with id {counsellor_id} not found")
                return Response(
                    {'error': 'Counsellor not found'},
                    status=status.HTTP_404_NOT_FOUND
                )

            # Validate amount
            if not isinstance(amount, (int, float)) or amount <= 0:
                logger.warning(f"Invalid amount: {amount}")
                return Response(
                    {'error': 'Invalid amount. Must be a positive number.'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Simulate payout processing (no Razorpay integration yet)
            try:
                with transaction.atomic():
                    # Generate a temporary payout ID (to be replaced with Razorpay payout ID later)
                    import time
                    temp_payout_id = f'TEMP_POUT_{counsellor_id}_{int(amount)}_{int(time.time())}'
                    
                    # Save payout record in database
                    payout = Payout.objects.create(
                        counsellor=counsellor_profile,
                        amount=amount / 100,  # Convert back to INR for database
                        razorpay_payout_id=temp_payout_id,  # Temporary ID
                        status='pending',  # Default status
                        notes=notes
                    )

                    logger.info(f"Payout recorded for counsellor {counsellor_id}: {temp_payout_id}")
                    return Response({
                        'status': 'success',
                        'message': 'Payout recorded successfully (pending Razorpay integration)',
                        'payout_id': temp_payout_id,
                        'data': {
                            'payout_id': payout.id,
                            'razorpay_payout_id': temp_payout_id,
                            'amount': amount / 100,  # Return in INR
                            'status': 'pending',
                            'created_at': payout.created_at
                        }
                    }, status=status.HTTP_201_CREATED)

            except Exception as e:
                logger.error(f"Error recording payout for counsellor {counsellor_id}: {str(e)}")
                return Response(
                    {'error': f'Error recording payout: {str(e)}'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

        except Exception as e:
            logger.error(f"Unexpected error in payout processing: {str(e)}")
            return Response(
                {'error': f'Unexpected error: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
  
  
class CounsellorPaymentSettingsAPIView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request, user_id=None):
        try:
            if user_id:
                try:
                    payment_settings = CounsellorPayment.objects.get(
                        counsellor__user__id=user_id,
                        counsellor__user_role='counsellor',
                        counsellor__user__is_admin=False
                    )
                    serializer = CounsellorPaymentSerializer(payment_settings)
                    return Response({
                        'status': 'success',
                        'data': serializer.data
                    }, status=status.HTTP_200_OK)
                except ObjectDoesNotExist:
                    logger.warning(f"Payment settings for user_id={user_id} not found")
                    return Response(
                        {'error': 'Payment settings not found for this counsellor'},
                        status=status.HTTP_404_NOT_FOUND
                    )
            else:
                payment_settings = CounsellorPayment.objects.filter(
                    counsellor__user_role='counsellor',
                    counsellor__user__is_admin=False
                ).select_related('counsellor__user')
                serializer = CounsellorPaymentSerializer(payment_settings, many=True)
                return Response({
                    'status': 'success',
                    'data': serializer.data
                }, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"Error fetching payment settings: {str(e)}")
            return Response(
                {'error': f'Error fetching payment settings: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def post(self, request):
        try:
            logger.debug(f"Creating payment settings with data: {request.data}")
            required_fields = ['user_id', 'session_fee', 'session_duration']
            missing_fields = [field for field in required_fields if field not in request.data]
            if missing_fields:
                logger.error(f"Missing required fields: {missing_fields}")
                return Response(
                    {'error': f'Missing required fields: {", ".join(missing_fields)}'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            user_id = request.data['user_id']
            try:
                counsellor_profile = UserProfile.objects.get(
                    user__id=user_id,
                    user_role='counsellor',
                    user__is_admin=False
                )
            except ObjectDoesNotExist:
                logger.warning(f"Counsellor with user_id={user_id} not found")
                return Response(
                    {'error': 'Counsellor not found'},
                    status=status.HTTP_404_NOT_FOUND
                )

            if CounsellorPayment.objects.filter(counsellor=counsellor_profile).exists():
                logger.warning(f"Payment settings already exist for user_id={user_id}")
                return Response(
                    {'error': 'Payment settings already exist for this counsellor'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            serializer = CounsellorPaymentSerializer(data=request.data)
            if serializer.is_valid():
                with transaction.atomic():
                    serializer.save(counsellor=counsellor_profile)
                    logger.info(f"Payment settings created for user_id={user_id}")
                    return Response({
                        'status': 'success',
                        'message': 'Payment settings created successfully',
                        'data': serializer.data
                    }, status=status.HTTP_201_CREATED)
            else:
                logger.warning(f"Validation failed for payment settings: {serializer.errors}")
                return Response(
                    serializer.errors,
                    status=status.HTTP_400_BAD_REQUEST
                )
        except Exception as e:
            logger.error(f"Error creating payment settings: {str(e)}")
            return Response(
                {'error': f'Error creating payment settings: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def patch(self, request, user_id):
        try:
            logger.debug(f"Updating payment settings for user_id={user_id}, data={request.data}")
            try:
                payment_settings = CounsellorPayment.objects.get(
                    counsellor__user__id=user_id,
                    counsellor__user_role='counsellor',
                    counsellor__user__is_admin=False
                )
            except ObjectDoesNotExist:
                logger.warning(f"Payment settings for user_id={user_id} not found")
                return Response(
                    {'error': 'Payment settings not found for this counsellor'},
                    status=status.HTTP_404_NOT_FOUND
                )

            serializer = CounsellorPaymentSerializer(payment_settings, data=request.data, partial=True)
            if serializer.is_valid():
                with transaction.atomic():
                    serializer.save()
                    logger.info(f"Payment settings updated for user_id={user_id}")
                    return Response({
                        'status': 'success',
                        'message': 'Payment settings updated successfully',
                        'data': serializer.data
                    }, status=status.HTTP_200_OK)
            else:
                logger.warning(f"Validation failed for payment settings update: {serializer.errors}")
                return Response(
                    serializer.errors,
                    status=status.HTTP_400_BAD_REQUEST
                )
        except Exception as e:
            logger.error(f"Error updating payment settings for user_id={user_id}: {str(e)}")
            return Response(
                {'error': f'Error updating payment settings: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
            
from rest_framework.parsers import MultiPartParser, FormParser
class ProblemAPIView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = (MultiPartParser, FormParser)


    def get(self, request):
        """Retrieve all problems or user's selected problems."""
        if request.query_params.get('selected'):
            # Get problems selected by the authenticated user
            user_profile = UserProfile.objects.get(user=request.user)
            user_problems = UserProblem.objects.filter(user_profile=user_profile)
            serializer = UserProblemSerializer(user_problems, many=True)
            return Response(serializer.data)
        else:
            # Get all problems
            problems = Problem.objects.all()
            serializer = ProblemSerializer(problems, many=True)
            return Response(serializer.data)

    def post(self, request):
        """Create a new problem."""
        serializer = ProblemSerializer(data=request.data)
        if serializer.is_valid():
            user_profile = UserProfile.objects.get(user=request.user)
            if user_profile.user_role in ['admin', 'counsellor']:  # Restrict to admin/counsellor
                serializer.save(created_by=user_profile)
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response({"error": "Only admins or counsellors can create problems"}, status=status.HTTP_403_FORBIDDEN)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def put(self, request, pk):
        """Update a problem."""
        try:
            problem = Problem.objects.get(pk=pk)
        except Problem.DoesNotExist:
            return Response({"error": "Problem not found"}, status=status.HTTP_404_NOT_FOUND)
        
        user_profile = UserProfile.objects.get(user=request.user)
        if user_profile.user_role not in ['admin', 'counsellor']:
            return Response({"error": "Only admins or counsellors can update problems"}, status=status.HTTP_403_FORBIDDEN)
        
        serializer = ProblemSerializer(problem, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)



    def delete(self, request, pk):
        """Delete a problem."""
        try:
            problem = Problem.objects.get(pk=pk)
        except Problem.DoesNotExist:
            return Response({"error": "Problem not found"}, status=status.HTTP_404_NOT_FOUND)
        
        user_profile = UserProfile.objects.get(user=request.user)
        if user_profile.user_role not in ['admin', 'counsellor']:
            return Response({"error": "Only admins or counsellors can delete problems"}, status=status.HTTP_403_FORBIDDEN)
        
        problem.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)





class UserProblemAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        """Allow a user to select a problem."""
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

    def get(self, request):
        """Retrieve all problems selected by the authenticated user."""
        user_profile = UserProfile.objects.get(user=request.user)
        user_problems = UserProblem.objects.filter(user_profile=user_profile)
        serializer = UserProblemSerializer(user_problems, many=True)
        return Response(serializer.data)            
                     
                    