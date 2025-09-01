import firebase_admin
from firebase_admin import credentials
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

import json

# Initialize Firebase Admin SDK
cred_json = os.getenv('FIREBASE_CREDENTIALS')
if not cred_json:
    raise ValueError("FIREBASE_CREDENTIALS environment variable not set.")
cred_dict = json.loads(cred_json)  # convert string to dict
cred = credentials.Certificate(cred_dict)
firebase_admin.initialize_app(cred)