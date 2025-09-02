


from firebase_admin import auth
from django.contrib.auth import get_user_model
from rest_framework import authentication
from rest_framework import exceptions
import logging
from django.contrib.auth.backends import ModelBackend

logger = logging.getLogger(__name__)


class FirebaseAuthentication(authentication.BaseAuthentication):
    def authenticate(self, request):
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return None

        try:
            id_token = auth_header.split(' ').pop()
            decoded_token = auth.verify_id_token(id_token)
        except Exception as e:
            logging.error(f"Failed to decode Firebase ID token: {e}")
            raise exceptions.AuthenticationFailed('Invalid Firebase ID token')

        if not id_token or not decoded_token:
            return None

        try:
            uid = decoded_token.get('uid')
            User = get_user_model()
            user, created = User.objects.get_or_create(firebase_uid=uid)
            if created:
                # You might want to populate the user model with more data from the decoded_token
                # For example: user.email = decoded_token.get('email')
                user.save()
            return (user, None)
        except Exception as e:
            logging.error(f"Failed to get or create user from Firebase UID: {e}")
            raise exceptions.AuthenticationFailed('User authentication failed')

logger = logging.getLogger(__name__)

class PhoneNumberBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        logger.debug(f"Attempting to authenticate user with phone number: {username}")
        UserModel = get_user_model()
        try:
            user = UserModel.objects.get(phone_number=username)
            logger.debug(f"User found: {user.phone_number}")
        except UserModel.DoesNotExist:
            logger.debug(f"User with phone number {username} not found.")
            return None

        if user.check_password(password):
            logger.debug(f"Password check successful for user: {user.phone_number}")
            return user
        else:
            logger.debug(f"Password check failed for user: {user.phone_number}")
            return None


    def get_user(self, user_id):
        UserModel = get_user_model()
        try:
            return UserModel.objects.get(pk=user_id)
        except UserModel.DoesNotExist:
            return None