from rest_framework import serializers
from .models import CallRequest, Booking
from userdetails.models import Wallet, WalletTransaction
from userdetails.serializers import UserSerializer, UserProfileSerializer
from userdetails.models import Wallet, WalletTransaction
class BookingSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    counsellor = UserProfileSerializer(read_only=True)

    class Meta:
        model = Booking
        fields = ['id', 'user', 'counsellor', 'order_id', 'amount', 'status', 'created_at', 'scheduled_at', 'session_duration']        
        
class CallRequestSerializer(serializers.ModelSerializer):
    booking = BookingSerializer(read_only=True)
    user = UserSerializer(read_only=True)
    counsellor = UserProfileSerializer(read_only=True)

    class Meta:
        model = CallRequest
        fields = ['id', 'booking', 'user', 'counsellor', 'status', 'requested_at', 'updated_at', 'scheduled_at', 'accepted_at', 'ended_at']
        
        
        

class WalletSerializer(serializers.ModelSerializer):
    class Meta:
        model = Wallet
        fields = ['balance', 'created_at', 'updated_at']

class WalletTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = WalletTransaction
        fields = ['amount', 'transaction_type', 'description', 'created_at', 'related_booking']        