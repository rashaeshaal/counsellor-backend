from rest_framework import serializers
from django.core.validators import RegexValidator
import re
from userdetails.models import User, UserProfile, OTPAttempt
from .models import CounsellorPayment




class CounsellorPaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = CounsellorPayment
        fields = ['session_fee', 'session_duration', 'updated_at']
        read_only_fields = ['updated_at']




