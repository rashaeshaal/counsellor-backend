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

            if message_type in ['offer', 'answer', 'ice-candidate', 'call-ended', 'call-rejected', 'media-toggle']:
                await self.handle_webrtc_message(data)
            elif message_type == 'call_initiated':
                await self.handle_call_initiated(data)
            elif message_type == 'call_accepted':
                await self.handle_call_accepted(data)
            else:
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
    
    async def handle_call_initiated(self, data):
        data['sender_id'] = self.user_id
        data['is_from_counsellor'] = self.is_counsellor
        await self.channel_layer.group_send(
            self.group_name,
            {
                'type': 'call_notification',
                'message': {
                    'type': 'call_initiated',
                    'booking_id': str(self.booking_id),
                    'user_id': self.user_id,
                    'user_name': data.get('user_name', 'Client'),
                    'timestamp': int(timezone.now().timestamp())
                }
            }
        )
        logger.info(f"Call initiated notification sent for booking {self.booking_id}")

    async def handle_webrtc_message(self, data):
        """Handle WebRTC signaling messages (offer, answer, ice-candidate)"""
        data['sender_id'] = getattr(self, 'user_id', None)
        data['is_from_counsellor'] = getattr(self, 'is_counsellor', False)
        
        await self.channel_layer.group_send(
            self.group_name,
            {
                'type': 'call_notification',
                'message': data
            }
        )
        logger.info(f"Forwarded WebRTC message to group {self.group_name}: {data['type']}")
    
    async def handle_call_accepted(self, data):
        data['sender_id'] = self.user_id
        data['is_from_counsellor'] = self.is_counsellor
        await self.channel_layer.group_send(
            self.group_name,
            {
                'type': 'call_notification',
                'message': {
                    'type': 'call_accepted',
                    'booking_id': str(self.booking_id),
                    'counsellor_id': self.user_id,
                    'counsellor_name': data.get('counsellor_name', 'Counsellor'),
                    'timestamp': int(timezone.now().timestamp())
                }
            }
        )
        logger.info(f"Call accepted notification sent for booking {self.booking_id}")

    async def handle_call_rejected(self, data):
        """Handle call rejection"""
        await self.update_call_status('REJECTED')
        await self.channel_layer.group_send(
            self.group_name,
            {
                'type': 'call_notification',
                'message': {
                    'type': 'call_rejected',
                    'booking_id': str(self.booking_id),
                    'timestamp': int(timezone.now().timestamp())
                }
            }
        )
        logger.info(f"Call rejected for booking {self.booking_id}")

    async def handle_call_ended(self, data):
        """Handle call ending"""
        await self.update_call_status('ENDED')
        await self.channel_layer.group_send(
            self.group_name,
            {
                'type': 'call_notification',
                'message': {
                    'type': 'call_ended',
                    'booking_id': str(self.booking_id),
                    'ended_by': getattr(self, 'user_id', None),
                    'timestamp': int(timezone.now().timestamp())
                }
            }
        )
        logger.info(f"Call ended for booking {self.booking_id} by user {getattr(self, 'user_id', 'unknown')}")

    async def handle_media_toggle(self, data):
        """Handle media toggle events"""
        data['sender_id'] = getattr(self, 'user_id', None)
        data['is_from_counsellor'] = getattr(self, 'is_counsellor', False)
        
        await self.channel_layer.group_send(
            self.group_name,
            {
                'type': 'call_notification',
                'message': data
            }
        )
        logger.info(f"Media toggle for booking {self.booking_id}: {data.get('mediaType')} = {data.get('enabled')}")

    async def call_notification(self, event):
        """Send notification to client"""
        message = event['message']
        await self.send(text_data=json.dumps(message))
        logger.debug(f"Sent call notification for booking {self.booking_id}: {message.get('type', 'unknown')}")

    async def check_pending_call(self):
        """Check if there's a pending call for this booking when counsellor connects"""
        call_request = await self.get_pending_call_request()
        if call_request:
            user_name = await self.get_user_name_from_call_request(call_request)
            await self.send(text_data=json.dumps({
                'type': 'call_initiated',
                'booking_id': str(self.booking_id),
                'user_name': user_name,
                'timestamp': int(timezone.now().timestamp()),
                'message': 'Pending call detected'
            }))
            logger.info(f"Notified counsellor of pending call for booking {self.booking_id}")

    @database_sync_to_async
    def get_user_from_token(self, token_key):
        try:
            token = AccessToken(token_key)
            user_id = token['user_id']
            User = get_user_model()
            user = User.objects.get(id=user_id)
            logger.info(f"Found user {user_id} for token, type: {type(user)}")
            return user
        except Exception as e:
            logger.error(f"Token validation failed: {e}")
            return None

    @database_sync_to_async
    def check_booking_exists(self):
        try:
            from .models import Booking
            exists = Booking.objects.filter(id=self.booking_id).exists()
            logger.info(f"Booking {self.booking_id} exists: {exists}")
            return exists
        except Exception as e:
            logger.error(f"Error checking booking {self.booking_id}: {e}")
            return False

    @database_sync_to_async
    def check_if_counsellor(self, user):
        """Check if user is a counsellor by examining their profile"""
        try:
            from .models import UserProfile
            profile = user.profile
            is_counsellor = profile.user_role == 'counsellor' and profile.is_active
            logger.info(f"User {user.id} is_counsellor: {is_counsellor} (role: {profile.user_role}, active: {profile.is_active})")
            return is_counsellor
        except UserProfile.DoesNotExist:
            logger.warning(f"User {user.id} does not have a profile")
            return False
        except Exception as e:
            logger.error(f"Error checking if user {user.id} is counsellor: {e}")
            return False

    @database_sync_to_async
    def get_pending_call_request(self):
        try:
            from .models import CallRequest
            return CallRequest.objects.filter(
                booking_id=self.booking_id,
                status='PENDING'
            ).order_by('-created_at').first()
        except Exception as e:
            logger.error(f"Error getting pending call request for booking {self.booking_id}: {e}")
            return None

    @database_sync_to_async
    def get_user_name_from_call_request(self, call_request):
        try:
            user = call_request.user
            user_full_name = user.get_full_name().strip()
            return user_full_name or user.username or f"User {user.id}"
        except Exception as e:
            logger.error(f"Error getting user name from call request: {e}")
            return "Client"

    @database_sync_to_async
    def update_call_status(self, status):
        try:
            from .models import CallRequest
            call_request = CallRequest.objects.filter(
                booking_id=self.booking_id
            ).order_by('-created_at').first()
            
            if call_request:
                call_request.status = status
                if status == 'ENDED':
                    call_request.ended_at = timezone.now()
                call_request.save()
                logger.info(f"Updated call request status to {status} for booking {self.booking_id}")
            else:
                logger.warning(f"No call request found to update for booking {self.booking_id}")
        except Exception as e:
            logger.error(f"Error updating call status for booking {self.booking_id}: {e}")