from rest_framework import serializers
from django.core.validators import RegexValidator
import re
from userdetails.models import User, UserProfile, OTPAttempt
from .models import CounsellorPayment






class CounsellorPaymentSerializer(serializers.ModelSerializer):
    user_id = serializers.IntegerField(source='counsellor.user.id', read_only=True)
    counsellor_name = serializers.CharField(source='counsellor.name', read_only=True)

    class Meta:
        model = CounsellorPayment
        fields = ['user_id', 'counsellor_name', 'session_fee', 'session_duration', 'updated_at']
        read_only_fields = ['user_id','updated_at', 'counsellor_name']

    def update(self, instance, validated_data):
        instance.session_fee = validated_data.get('session_fee', instance.session_fee)
        instance.session_duration = validated_data.get('session_duration', instance.session_duration)
        instance.save()
        return instance

