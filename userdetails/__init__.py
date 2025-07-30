import firebase_admin
from firebase_admin import credentials
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

# Initialize Firebase Admin SDK
cred_path = os.getenv('FIREBASE_CRED_PATH')
if not os.path.exists(cred_path):
    raise FileNotFoundError(f"Firebase credentials file not found at: {cred_path}")
cred = credentials.Certificate(cred_path)
firebase_admin.initialize_app(cred)