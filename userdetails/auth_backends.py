import logging
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model

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
