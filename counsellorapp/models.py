from django.db import models
from userdetails.models import UserProfile
# Create your models here.


class CounsellorPayment(models.Model):
    counsellor = models.OneToOneField(UserProfile, on_delete=models.CASCADE, related_name='payment_settings')
    session_fee = models.DecimalField(max_digits=10, decimal_places=2, default=50.00)  # In INR
    session_duration = models.IntegerField(default=20)  # In minutes
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.counsellor.name} - ₹{self.session_fee} for {self.session_duration} minutes"    