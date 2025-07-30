from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'^ws/call/(?P<booking_id>\d+)/$', consumers.CallConsumer.as_asgi()),
]