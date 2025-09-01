from rest_framework import serializers
from dashboard.models import Booking
from .models import CounsellorPayment

class UpcomingSessionSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()
    booking_id = serializers.IntegerField(source='id')
    scheduled_time = serializers.DateTimeField(source='scheduled_at')

    class Meta:
        model = Booking
        fields = ['booking_id', 'user_name', 'scheduled_time', 'session_duration']

    def get_user_name(self, obj):
        if obj.user and hasattr(obj.user, 'user'):
            return obj.user.user.get_full_name() or obj.user.user.username
        return "Anonymous"

class RecentActivitySerializer(serializers.Serializer):
    activity_id = serializers.IntegerField()
    type = serializers.CharField()
    description = serializers.CharField()
    timestamp = serializers.DateTimeField()

class CounsellorPaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = CounsellorPayment
        fields = ['counsellor', 'session_fee', 'session_duration', 'updated_at']
        read_only_fields = ['counsellor']
