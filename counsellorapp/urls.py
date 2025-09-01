from django.urls import path
from .views import UpcomingSessionsView, RecentActivityView

urlpatterns = [
    path('upcoming-sessions/', UpcomingSessionsView.as_view(), name='upcoming-sessions'),
    path('recent-activity/', RecentActivityView.as_view(), name='recent-activity'),
]
