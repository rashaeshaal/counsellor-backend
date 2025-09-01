from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from dashboard.models import Booking
from .serializers import UpcomingSessionSerializer
from django.utils import timezone
from userdetails.auth_backends import FirebaseAuthentication

class UpcomingSessionsView(APIView):
    authentication_classes = [FirebaseAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            counsellor = request.user.userprofile.counsellor
        except AttributeError:
            return Response({"detail": "Counsellor profile not found for the current user."}, status=404)

        now = timezone.now()
        upcoming_sessions = Booking.objects.filter(
            counsellor=counsellor,
            scheduled_at__gte=now,
            status='scheduled'
        ).order_by('scheduled_at')
        
        serializer = UpcomingSessionSerializer(upcoming_sessions, many=True)
        return Response(serializer.data)

from .serializers import RecentActivitySerializer
from itertools import chain

class RecentActivityView(APIView):
    authentication_classes = [FirebaseAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            counsellor = request.user.userprofile.counsellor
        except AttributeError:
            return Response({"detail": "Counsellor profile not found for the current user."}, status=404)

        completed_calls = Booking.objects.filter(counsellor=counsellor, status='completed').order_by('-updated_at')[:10]
        new_bookings = Booking.objects.filter(counsellor=counsellor, status='scheduled').order_by('-created_at')[:10]

        activities = []
        for call in completed_calls:
            activities.append({
                'activity_id': call.id,
                'type': 'Completed Call',
                'description': f"Completed a {call.session_duration}-minute call with {call.user.user.get_full_name() or call.user.user.username}.",
                'timestamp': call.updated_at
            })

        for booking in new_bookings:
            activities.append({
                'activity_id': booking.id,
                'type': 'New Call',
                'description': f"New {booking.session_duration}-minute session call by {booking.user.user.get_full_name() or booking.user.user.username}.",
                'timestamp': booking.created_at
            })

        # Sort activities by timestamp
        activities.sort(key=lambda x: x['timestamp'], reverse=True)
        
        # Limit to recent 20 activities
        activities = activities[:20]

        serializer = RecentActivitySerializer(activities, many=True)
        return Response(serializer.data)