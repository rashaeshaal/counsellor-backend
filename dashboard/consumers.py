import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from rest_framework_simplejwt.tokens import AccessToken
from userdetails.models import User

class CounsellorConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.counsellor_id = self.scope['url_route']['kwargs']['counsellor_id']
        self.group_name = f"counsellor_{self.counsellor_id}"

        # Extract token from query parameters
        query_string = self.scope.get('query_string', b'').decode()
        token = None
        
        if 'token=' in query_string:
            token = query_string.split('token=')[1].split('&')[0]
        
        if not token:
            print(f"[WebSocket] Connection rejected: No token provided for counsellor_{self.counsellor_id}")
            await self.close(code=4001)
            return

        try:
            # Verify JWT token
            access_token = AccessToken(token)
            user_profile = await database_sync_to_async(UserProfile.objects.get)(user_id=access_token['user_id'])
            if str(user_profile.id) != str(self.counsellor_id):
                print(f"[WebSocket] Connection rejected: Profile ID {user_profile.id} does not match counsellor_id {self.counsellor_id}")
                await self.close(code=4003)
                return
                
            print(f"[WebSocket] Connection accepted for counsellor_{self.counsellor_id}")
            
        except Exception as e:
            print(f"[WebSocket] Connection rejected: Invalid token for counsellor_{self.counsellor_id} - {str(e)}")
            await self.close(code=4002)
            return

        try:
            # Add to group and accept connection
            await self.channel_layer.group_add(self.group_name, self.channel_name)
            await self.accept()
            
            # Send connection confirmation
            await self.send(text_data=json.dumps({
                'type': 'connection_established',
                'message': 'WebSocket connected successfully'
            }))
        except Exception as e:
            print(f"[WebSocket] Error during connection setup for counsellor_{self.counsellor_id}: {str(e)}")
            await self.close(code=4004)

    async def disconnect(self, close_code):
        print(f"[WebSocket] Disconnected for counsellor_{self.counsellor_id} with code: {close_code}")
        # Remove from group
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    # Receive message from room group
    async def call_notification(self, event):
        try:
            print(f"[WebSocket] Sending call_notification to counsellor_{self.counsellor_id}: {event}")
            
            # Send message to WebSocket
            await self.send(text_data=json.dumps({
                'type': 'call_notification',
                'room_id': event['room_id'],
                'kitToken': event['kitToken'],
                'user_id': event['user_id'],
                'booking_id': event['booking_id'],
                'counsellor_id': event.get('counsellor_id'),
                'message': f"Incoming call from user {event['user_id']}"
            }))
        except Exception as e:
            print(f"[WebSocket] Error in call_notification for counsellor_{self.counsellor_id}: {str(e)}")

    # Handle other message types
    async def notification_message(self, event):
        await self.send(text_data=json.dumps({
            'type': 'notification',
            'message': event['message'],
            'title': event.get('title', 'Notification')
        }))