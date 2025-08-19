from django.db import models
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.core.validators import RegexValidator

# Custom User Manager
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.core.validators import RegexValidator
from django.db import models
from django.core.exceptions import ValidationError

class CustomUserManager(BaseUserManager):
    def normalize_phone_number(self, phone_number):
        # Normalize phone number (e.g., remove spaces, dashes)
        return phone_number.replace(" ", "").replace("-", "")

    def create_user(self, phone_number, password=None, **extra_fields):
        if not phone_number:
            raise ValueError("The Phone Number field must be set")
        phone_number = self.normalize_phone_number(phone_number)
        user = self.model(phone_number=phone_number, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, phone_number, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_admin", True)
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        return self.create_user(phone_number, password, **extra_fields)

class User(AbstractUser):
    username = None
    email = None
    
    phone_regex = RegexValidator(
        regex=r'^\+?1?\d{9,15}$',
        message="Phone number must be entered in the format: '+999999999'. Up to 15 digits allowed."
    )
    phone_number = models.CharField(
        validators=[phone_regex],
        max_length=17,
        unique=True,
        help_text="Phone number with country code"
    )
    email = models.EmailField(unique=True, blank=True, null=True)
    is_admin = models.BooleanField(default=False)
    firebase_uid = models.CharField(max_length=255, blank=True, null=True, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = 'phone_number'
    REQUIRED_FIELDS = ['email']

    objects = CustomUserManager()

    def __str__(self):
        return self.phone_number

class UserProfile(models.Model):
    USER_TYPE_CHOICES = [
        ('normal', 'Normal User'),
        ('counsellor', 'Counsellor'),
        ('admin', 'Admin'),
    ]
    
    GENDER_CHOICES = [
        ('M', 'Male'),
        ('F', 'Female'),
        ('O', 'Other'),
    ]
    
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='profile'
    )
    user_role = models.CharField(
        max_length=20,
        choices=USER_TYPE_CHOICES,
        default='normal',
    )
    phone_number = models.CharField(
        validators=[RegexValidator(
            regex=r'^\+?1?\d{9,15}$',
            message="Phone number must be entered in the format: '+999999999'. Up to 15 digits allowed."
        )],
        max_length=17,
        unique=True,
        help_text="Phone number with country code"
    )
    name = models.CharField(max_length=100, blank=True, null=True)
    email = models.EmailField(unique=True, blank=True, null=True)
    age = models.IntegerField(blank=True, null=True)
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES, blank=True, null=True)
    qualification = models.TextField(max_length=500, blank=True, null=True)
    experience = models.IntegerField(blank=True, null=True)
    google_pay_number = models.CharField(max_length=15, blank=True, null=True)
    account_number = models.CharField(max_length=20, blank=True, null=True)
    ifsc_code = models.CharField(max_length=11, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_approved = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    profile_photo = models.ImageField(upload_to='profile_photos/', null=True, blank=True)
    firebase_uid = models.CharField(max_length=255, blank=True, null=True, unique=True)
    razorpay_contact_id = models.CharField(max_length=100, blank=True, null=True)
    razorpay_fund_account_id = models.CharField(max_length=100, blank=True, null=True)
   
    def clean(self):
        # Ensure phone_number matches user.phone_number
        if self.phone_number != self.user.phone_number:
            raise ValidationError("UserProfile phone_number must match User phone_number.")

    def save(self, *args, **kwargs):
        # Sync phone_number with user.phone_number
        if not self.phone_number:
            self.phone_number = self.user.phone_number
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name or self.user.phone_number


       

# OTP Model for tracking OTP attempts
class OTPAttempt(models.Model):
    phone_number = models.CharField(max_length=17)
    otp_sent_at = models.DateTimeField(auto_now_add=True)
    attempts = models.PositiveIntegerField(default=0)
    is_verified = models.BooleanField(default=False)
    
    class Meta:
        verbose_name = "OTP Attempt"
        verbose_name_plural = "OTP Attempts"

    def __str__(self):
        return f"OTP for {self.phone_number}"
    




class Wallet(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='wallet')
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    extra_minutes = models.IntegerField(default=0) # New field for extra minutes
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Wallet for {self.user.username}: {self.balance}"

class WalletTransaction(models.Model):
    TRANSACTION_TYPES = [
        ('DEPOSIT', 'Deposit'),
        ('TRANSFER', 'Transfer'),
        ('WITHDRAWAL', 'Withdrawal'),
        ('EXTRA_MINUTES_CREDIT', 'Extra Minutes Credit'), # New transaction type
    ]

    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE, related_name='transactions')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    description = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    related_booking = models.ForeignKey('dashboard.Booking', on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return f"{self.transaction_type} of {self.amount} for {self.wallet.user.username}"    

    
    
    
    
    
    