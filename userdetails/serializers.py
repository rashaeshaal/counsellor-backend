from rest_framework import serializers
from django.core.validators import RegexValidator
import re
from .models import User, UserProfile
from counsellorapp.serializers import CounsellorPaymentSerializer
from counsellorapp.models import CounsellorPayment


class MappedChoiceField(serializers.ChoiceField):
    def to_internal_value(self, data):
        # First, try the parent's implementation. This will handle keys.
        try:
            return super().to_internal_value(data)
        except serializers.ValidationError:
            # If that fails, try to match by display name.
            for key, display_name in self.choices.items():
                if str(display_name).lower() == str(data).lower():
                    return key
            # If both fail, re-raise the validation error.
            self.fail('invalid_choice', input=data)


class FirebaseAuthSerializer(serializers.Serializer):
    id_token = serializers.CharField(required=True)

    def validate_id_token(self, value):
        if not value:
            raise serializers.ValidationError("Firebase ID token is required")
        return value
class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'phone_number', 'is_admin', 'firebase_uid', 'created_at']
        read_only_fields = ['id', 'created_at']

class UserProfileSerializer(serializers.ModelSerializer):
    age = serializers.IntegerField(required=True, min_value=0)
    experience = serializers.IntegerField(required=True, min_value=0)
    email = serializers.EmailField(required=True)
    phone_number = serializers.CharField(required=True)

    def __init__(self, *args, **kwargs):
        data = kwargs.get('data')
        if data:
            cleaned_data = {}
            for key, value in data.items():
                if isinstance(value, list) and len(value) == 1:
                    cleaned_data[key] = value[0]
                else:
                    cleaned_data[key] = value
            kwargs['data'] = cleaned_data
        super().__init__(*args, **kwargs)

    def validate(self, data):
        phone_number = data.get('phone_number')
        email = data.get('email')

        if User.objects.filter(phone_number=phone_number).exists():
            raise serializers.ValidationError({"phone_number": "A user with this phone number already exists."})
        if User.objects.filter(email=email).exists():
            raise serializers.ValidationError({"email": "A user with this email already exists."})

        if data.get('user_role') == 'counsellor':
            required_fields = [
                'name', 'email', 'age', 'gender', 'qualification',
                'experience', 'google_pay_number', 'account_number', 'ifsc_code'
            ]
            for field in required_fields:
                if not data.get(field):
                    raise serializers.ValidationError({field: f"{field} is required for counsellors."})
        return data

    def validate_age(self, value):
        if value and (int(value) < 18 or int(value) > 100):
            raise serializers.ValidationError("Age must be between 18 and 100.")
        return value

    def create(self, validated_data):
        user = self.context.get('user')
        if not user:
            raise serializers.ValidationError("User must be provided to create a UserProfile.")
        return UserProfile.objects.create(user=user, **validated_data)

    class Meta:
        model = UserProfile
        fields = [
            'id','user_role', 'phone_number', 'name', 'email', 'age', 'gender',
            'qualification', 'experience', 'google_pay_number', 'account_number',
            'ifsc_code', 'is_approved', 'is_active', 'profile_photo', 'firebase_uid','user_id'
        ]
        read_only_fields = ['user',  'firebase_uid']


class PhoneNumberSerializer(serializers.Serializer):
    phone_number = serializers.CharField(required=True)

    def validate_phone_number(self, value):
        phone_regex = RegexValidator(
            regex=r'^\+?1?\d{9,15}$',
            message="Phone number must be entered in the format: '+999999999'. Up to 15 digits allowed."
        )
        phone_regex(value)
        return value

class OTPVerificationSerializer(serializers.Serializer):
    phone_number = serializers.CharField(required=True)
    otp = serializers.CharField(required=True, min_length=6, max_length=6)

    def validate_phone_number(self, value):
        phone_regex = RegexValidator(
            regex=r'^\+?1?\d{9,15}$',
            message="Phone number must be entered in the format: '+999999999'. Up to 15 digits allowed."
        )
        phone_regex(value)
        return value
    
class UserProfileUpdateSerializer(serializers.ModelSerializer):
    gender = MappedChoiceField(choices=UserProfile.GENDER_CHOICES, required=False)
    class Meta:
        model = UserProfile
        fields = ['name', 'age', 'gender']
