import time
import random
import hmac
import hashlib
import json
from base64 import b64encode

def generate_token(app_id, server_secret, user_id, room_id, privilege_expire_in_seconds=3600):
    """
    Generates a Zego Cloud Kit Token.
    """
    payload = {
        "app_id": app_id,
        "user_id": user_id,
        "room_id": room_id,
        "privileges": {
            "1": 1,  # loginRoom
            "2": 1   # publishStream
        },
        "nonce": random.randint(0, 2**32 - 1),
        "iat": int(time.time()),
        "exp": int(time.time()) + privilege_expire_in_seconds
    }

    payload_str = json.dumps(payload)

    # 1. Create HMAC-SHA256 signature
    key = server_secret.encode('utf-8')
    msg = payload_str.encode('utf-8')
    signature = hmac.new(key, msg, hashlib.sha256).digest()

    # 2. Combine parts for the final token
    token_data = {
        "ver": "04",
        "iv": b64encode(b'').decode('utf-8'), # IV is empty for this version
        "ciphertext": b64encode(signature).decode('utf-8'),
        "data": b64encode(payload_str.encode('utf-8')).decode('utf-8')
    }

    return "04" + b64encode(json.dumps(token_data).encode('utf-8')).decode('utf-8')
