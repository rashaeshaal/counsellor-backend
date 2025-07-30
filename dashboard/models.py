from django.db import models
from userdetails.models import User, UserProfile
from django.utils import timezone

# Create your models here.


class Booking(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('wallet_credited', 'Wallet Credited'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    counsellor = models.ForeignKey(UserProfile, on_delete=models.CASCADE)
    order_id = models.CharField(max_length=100)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    razorpay_payment_id = models.CharField(max_length=100, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    scheduled_at = models.DateTimeField(null=True, blank=True) 

    def __str__(self):
        return f"Booking {self.order_id} for {self.counsellor.name}"
    

class CallRequest(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('ACCEPTED', 'Accepted'),
        ('REJECTED', 'Rejected'),
        ('ENDED', 'Ended'),
    ]
    
    counsellor = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='call_requests')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='call_requests')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    scheduled_at = models.DateTimeField(null=True, blank=True)
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE)
    requested_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    

    class Meta:
        ordering = ['-requested_at']
        db_table = 'dashboard_callrequest' 
        
    def __str__(self):
        return f"Call Request {self.id} - {self.booking.id} - {self.status}"      
    
    
    
 
    
    
