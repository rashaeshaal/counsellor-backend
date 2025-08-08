from rest_framework import serializers
from django.core.validators import RegexValidator
import re
from .models import User, UserProfile
from counsellorapp.serializers import CounsellorPaymentSerializer
from counsellorapp.models import CounsellorPayment


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

    def validate(self, data):
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
        if value and (value < 18 or value > 100):
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
    class Meta:
        model = UserProfile
        fields = ['name', 'age', 'gender']
        
        extra_kwargs = {
            'name': {'required': True},
            'age': {'required': True},
            'gender': {'required': True}
        }