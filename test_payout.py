import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "counsellor_backend.settings")
django.setup()

from adminapp.views import PayoutAPIView
from rest_framework.test import APIRequestFactory
from userdetails.models import User

factory = APIRequestFactory()
request = factory.post('/api/admins/payout/', {'counsellor_id': 3, 'amount': 100})
user = User.objects.get(id=1)
request.user = user

view = PayoutAPIView.as_view()
response = view(request)
print(response.data)