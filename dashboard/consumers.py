import logging
import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from rest_framework_simplejwt.tokens import AccessToken
from django.contrib.auth import get_user_model
from django.utils import timezone

logger = logging.getLogger(__name__)

class CallConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        logger.info(f"WebSocket connection attempt for booking_id: {self.scope['url_route']['kwargs']['booking_id']}")
        
        self.booking_id = self.scope['url_route']['kwargs']['booking_id']
        self.group_name = f'call_{self.booking_id}'
        
        query_string = self.scope['query_string'].decode()
        token_key = None
        if 'token=' in query_string:
            token_key = query_string.split('token=')[-1].split('&')[0]
        
        if not token_key:
            logger.error(f"No token provided for booking {self.booking_id}")
            await self.close(code=4001)
            return

        user = await self.get_user_from_token(token_key)
        if not user:
            logger.error(f"Invalid token for booking {self.booking_id}")
            await self.close(code=4002)
            return

        logger.info(f"User retrieved: {user.id}, type: {type(user)}")
        booking_exists = await self.check_booking_exists()
        if not booking_exists:
            logger.error(f"Booking {self.booking_id} does not exist")
            await self.close(code=4003)
            return

        self.scope['user'] = user
        self.user_id = user.id
        self.is_counsellor = await self.check_if_counsellor(user)
        
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        await self.send(text_data=json.dumps({
            'type': 'connection_established',
            'booking_id': self.booking_id,
            'user_id': self.user_id,
            'is_counsellor': self.is_counsellor,
            'message': 'WebSocket connected successfully'
        }))

        logger.info(f"WebSocket connected for booking {self.booking_id}, user {user.id} ({'counsellor' if self.is_counsellor else 'client'}), group {self.group_name}")

        if self.is_counsellor:
            await self.check_pending_call()

    async def disconnect(self, close_code):
        logger.info(f"WebSocket disconnecting for booking {self.booking_id}, user {getattr(self, 'user_id', 'unknown')}, code={close_code}")
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)
        logger.info(f"WebSocket disconnected for booking {self.booking_id}")

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            message_type = data.get('type')
            logger.info(f"Received message type {message_type} for booking {self.booking_id} from user {self.user_id}")

            await self.channel_layer.group_send(
                self.group_name,
                {
                    'type': 'call_notification',
                    'message': data
                }
            )
                
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing WebSocket message for booking {self.booking_id}: {e}")
        except Exception as e:
            logger.error(f"Error handling WebSocket message for booking {self.booking_id}: {e}")
    
    

    
    
    

    

    

    

    

    

    

    

    

    

    

    