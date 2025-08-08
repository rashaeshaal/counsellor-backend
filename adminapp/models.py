from django.db import models
from django.conf import settings
from userdetails.models import UserProfile
from django.utils import timezone

class Payout(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('PROCESSING', 'Processing'),
        ('COMPLETED', 'Completed'),
        ('FAILED', 'Failed'),
    ]

    counsellor = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='payouts')
    admin = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='admin_payouts')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    razorpay_payout_id = models.CharField(max_length=100, null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    razorpay_contact_id = models.CharField(max_length=100, blank=True, null=True)
    razorpay_fund_account_id = models.CharField(max_length=100, blank=True, null=True)

    class Meta:
        ordering = ['-created_at']
        db_table = 'dashboard_payout'

    def __str__(self):
        return f"Payout {self.id} to {self.counsellor.name} - {self.status}"
    
 



class Problem(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    image = models.ImageField(upload_to='problems/', blank=True, null=True, help_text="Optional image for the problem.")
    created_by = models.ForeignKey(UserProfile,on_delete=models.SET_NULL,null=True,related_name='created_problems',help_text="The user who created this problem.")

    def __str__(self):
        return self.title

class UserProblem(models.Model):
    user_profile = models.ForeignKey(UserProfile,on_delete=models.CASCADE,related_name='selected_problems',help_text="The user who selected this problem.")
    problem = models.ForeignKey('Problem',on_delete=models.CASCADE,related_name='selected_by_users',help_text="The problem selected by the user.")
    selected_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user_profile', 'problem') 
        verbose_name = "User Problem"
        verbose_name_plural = "User Problems"

    def __str__(self):
        return f"{self.user_profile} - {self.problem}"    