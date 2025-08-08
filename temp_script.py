from userdetails.models import UserProfile
try:
    counsellor = UserProfile.objects.get(id=3)
    print(counsellor.account_number, counsellor.ifsc_code, counsellor.account_holder_name)
except UserProfile.DoesNotExist:
    print("Counsellor with ID 3 does not exist")