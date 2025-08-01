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


from .models import User, UserProfile, OTPAttempt
from .serializers import (
    UserSerializer, UserProfileSerializer, FirebaseAuthSerializer,
    PhoneNumberSerializer, OTPVerificationSerializer
)


if not firebase_admin._apps:
    if hasattr(settings, 'FIREBASE_SERVICE_ACCOUNT_KEY') and settings.FIREBASE_SERVICE_ACCOUNT_KEY:
        if isinstance(settings.FIREBASE_SERVICE_ACCOUNT_KEY, str):
            cred = credentials.Certificate(settings.FIREBASE_SERVICE_ACCOUNT_KEY)
        else:
            cred = credentials.Certificate(settings.FIREBASE_SERVICE_ACCOUNT_KEY)
    else:
        cred = credentials.ApplicationDefault()
    firebase_admin.initialize_app(cred)

logger = logging.getLogger(__name__)
User = get_user_model()


class FirebaseAuthView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = FirebaseAuthSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        id_token = serializer.validated_data['id_token']
        
        try:
            decoded_token = auth.verify_id_token(id_token)
            firebase_uid = decoded_token['uid']
            phone_number = decoded_token.get('phone_number')
            
            if not phone_number:
                return Response(
                    {'error': 'Phone number not found in token'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            user, created = User.objects.get_or_create(
                phone_number=phone_number,
                defaults={
                    'firebase_uid': firebase_uid,
                }
            )
            
            if not created and user.firebase_uid != firebase_uid:
                user.firebase_uid = firebase_uid
                user.save()
            
            # Create or update UserProfile for normal users with minimal fields
            profile, profile_created = UserProfile.objects.get_or_create(
                user=user,
                defaults={
                    'phone_number': phone_number,
                    'user_role': 'normal',  # Normal users only
                    'is_active': True,
                }
            )
            
            # Ensure user_role remains 'normal' for existing profiles
            if not profile_created and profile.user_role != 'normal':
                return Response(
                    {'error': 'This phone number is registered as a counsellor. Use counsellor login.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            refresh = RefreshToken.for_user(user)
            
            return Response({
                'refresh': str(refresh),
                'access': str(refresh.access_token),
                'user': UserSerializer(user).data,
                'profile': UserProfileSerializer(profile).data,
                'is_new_user': created and profile_created
            }, status=status.HTTP_200_OK)
            
        except auth.InvalidIdTokenError:
            return Response(
                {'error': 'Invalid Firebase ID token'},
                status=status.HTTP_401_UNAUTHORIZED
            )
        except auth.ExpiredIdTokenError:
            return Response(
                {'error': 'Firebase ID token has expired'},
                status=status.HTTP_401_UNAUTHORIZED
            )
        except auth.RevokedIdTokenError:
            return Response(
                {'error': 'Firebase ID token has been revoked'},
                status=status.HTTP_401_UNAUTHORIZED
            )
        except Exception as e:
            logger.error(f"Firebase login error: {str(e)}")
            return Response(
                {'error': 'Authentication failed'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class UserProfileRegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        logger.debug(f"Request data: {request.data}")
        phone_number = request.data.get('phone_number')
        required_fields = [
            'phone_number', 'name', 'email', 'age', 'gender', 'qualification',
            'experience', 'google_pay_number', 'account_number', 'ifsc_code'
        ]

        # Check for all required fields
        missing_fields = [field for field in required_fields if not request.data.get(field)]
        if missing_fields:
            logger.error(f"Missing fields: {missing_fields}")
            return Response(
                {'error': f'Missing required fields: {", ".join(missing_fields)}'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Check if a UserProfile with this phone number already exists
        if UserProfile.objects.filter(phone_number=phone_number).exists():
            logger.error(f"UserProfile with phone number {phone_number} already exists")
            return Response(
                {'error': 'UserProfile with this phone number already exists'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Create or get User for authentication
        try:
            user = User.objects.get(phone_number=phone_number)
            if hasattr(user, 'profile') and user.profile.user_role == 'counsellor':
                logger.error(f"User {phone_number} is already a counsellor")
                return Response(
                    {'error': 'User is already registered as a counsellor'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        except User.DoesNotExist:
            user = User.objects.create_user(phone_number=phone_number)
            logger.info(f"Created new User with phone_number {phone_number}")

        # Create UserProfile for counsellor
        serializer_data = request.data.copy()
        serializer_data['user_role'] = 'counsellor'
        serializer_data['is_approved'] = False
        serializer_data['is_active'] = request.data.get('is_active', True)
        
        serializer = UserProfileSerializer(data=serializer_data, context={'user': user})
        if serializer.is_valid():
            profile = serializer.save()
            refresh = RefreshToken.for_user(user)
            logger.info(f"Counsellor profile created for {phone_number}")
            return Response({
                'message': 'Counsellor registered successfully. Awaiting approval.',
                'refresh': str(refresh),
                'access': str(refresh.access_token),
                'user': UserSerializer(user).data,
                'profile': UserProfileSerializer(profile).data
            }, status=status.HTTP_201_CREATED)
        logger.error(f"Serializer errors: {serializer.errors}")
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    
class UserLoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        phone_number = request.data.get('phone_number', '').strip()
        print(f"Request phone number: {repr(phone_number)}")  # Debug: Log input

        if not phone_number:
            return Response({'error': 'Phone number is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            users = User.objects.filter(phone_number=phone_number)
            print(f"Found {users.count()} users with phone number: {repr(phone_number)}")  # Debug: Log user count

            if users.count() > 1:
                return Response({'error': 'Multiple users found with this phone number'}, status=status.HTTP_400_BAD_REQUEST)
            elif not users.exists():
                return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)

            user = users.first()
            print(f"Database phone number: {repr(user.phone_number)}")  # Debug: Log stored phone number

            try:
                profile = user.profile  # Access UserProfile
            except AttributeError as e:
                print(f"Profile access error: {str(e)}")  # Debug: Log profile error
                return Response({'error': 'User profile not found'}, status=status.HTTP_404_NOT_FOUND)

            refresh = RefreshToken.for_user(user)
            return Response({
                'refresh': str(refresh),
                'access': str(refresh.access_token),
                'user': UserSerializer(user).data,
                'profile': UserProfileSerializer(profile).data
            }, status=status.HTTP_200_OK)
        except User.DoesNotExist:  # Fallback for unexpected query issues
            print(f"Unexpected User.DoesNotExist for phone_number: {repr(phone_number)}")
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            print(f"Unexpected error: {str(e)}")  # Debug: Log unexpected errors
            return Response({'error': f'An unexpected error occurred: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)





