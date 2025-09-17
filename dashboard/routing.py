
# dashboard/routing.py
from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
        re_path(r'ws/counsellor/(?P<counsellor_id>\d+)/?$', consumers.CounsellorConsumer.as_asgi()),
]
