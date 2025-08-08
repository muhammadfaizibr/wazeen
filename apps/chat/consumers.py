# apps/chat/consumers.py (Missing database interaction methods)

import json
import uuid
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
import logging

from .models import ChatRoom, ChatMessage, ChatParticipant, TypingIndicator
from .serializers import ChatMessageSerializer, UserBasicSerializer

logger = logging.getLogger(__name__)
User = get_user_model()


class ChatConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for real-time chat functionality"""
    
    # ... existing connect, disconnect, receive methods ...
    
    @database_sync_to_async
    def check_room_access(self):
        """Check if user has access to the chat room"""
        try:
            room = ChatRoom.objects.select_related('request', 'request__client', 'request__accountant').get(
                id=self.room_id
            )
            return room.can_user_access(self.user)
        except ChatRoom.DoesNotExist:
            return False
    
    @database_sync_to_async
    def update_user_status(self, online=True):
        """Update user's online status in the chat room"""
        try:
            participant, created = ChatParticipant.objects.get_or_create(
                room_id=self.room_id,
                user=self.user,
                defaults={'is_active': True}
            )
            participant.last_seen = timezone.now()
            if created:
                participant.is_active = True
            participant.save(update_fields=['last_seen', 'is_active'])
            return True
        except Exception as e:
            logger.error(f"Error updating user status: {e}")
            return False
    
    @database_sync_to_async
    def set_typing_indicator(self, is_typing=True):
        """Set typing indicator for the user"""
        try:
            if is_typing:
                indicator, created = TypingIndicator.objects.update_or_create(
                    room_id=self.room_id,
                    user=self.user,
                    defaults={'is_typing': True, 'updated_at': timezone.now()}
                )
            else:
                TypingIndicator.objects.filter(
                    room_id=self.room_id,
                    user=self.user
                ).delete()
            return True
        except Exception as e:
            logger.error(f"Error setting typing indicator: {e}")
            return False
    
    @database_sync_to_async
    def remove_typing_indicator(self):
        """Remove typing indicator for the user"""
        try:
            TypingIndicator.objects.filter(
                room_id=self.room_id,
                user=self.user
            ).delete()
            return True
        except Exception as e:
            logger.error(f"Error removing typing indicator: {e}")
            return False
    
    @database_sync_to_async
    def create_message(self, content, message_type='text', file_id=None, parent_message_id=None):
        """Create a new chat message"""
        try:
            room = ChatRoom.objects.get(id=self.room_id)
            
            # Prepare message data
            message_data = {
                'room': room,
                'sender': self.user,
                'content': content,
                'message_type': message_type,
            }
            
            # Handle file attachment
            if file_id:
                from apps.file_management.models import File
                try:
                    file_obj = File.objects.get(id=file_id, is_deleted=False)
                    message_data['file'] = file_obj
                    
                    # Auto-detect message type based on file
                    if message_type == 'text':
                        if file_obj.mime_type.startswith('image/'):
                            message_data['message_type'] = 'image'
                        else:
                            message_data['message_type'] = 'document'
                except File.DoesNotExist:
                    logger.warning(f"File not found: {file_id}")
                    return None
            
            # Create the message
            message = ChatMessage.objects.create(**message_data)
            
            # Handle thread reply
            if parent_message_id:
                try:
                    from .models import MessageThread
                    parent_message = ChatMessage.objects.get(
                        id=parent_message_id,
                        room=room
                    )
                    MessageThread.objects.create(
                        parent_message=parent_message,
                        reply_message=message
                    )
                except ChatMessage.DoesNotExist:
                    logger.warning(f"Parent message not found: {parent_message_id}")
            
            # Update room's updated_at timestamp
            room.save(update_fields=['updated_at'])
            
            return message
            
        except Exception as e:
            logger.error(f"Error creating message: {e}")
            return None
    
    @database_sync_to_async
    def serialize_message(self, message):
        """Serialize message for WebSocket transmission"""
        try:
            serializer = ChatMessageSerializer(message)
            return serializer.data
        except Exception as e:
            logger.error(f"Error serializing message: {e}")
            return None
    
    @database_sync_to_async
    def mark_messages_as_read(self, message_id):
        """Mark messages as read up to the specified message"""
        try:
            room = ChatRoom.objects.get(id=self.room_id)
            message = ChatMessage.objects.get(id=message_id, room=room)
            
            # Get or create participant
            participant, created = ChatParticipant.objects.get_or_create(
                room=room,
                user=self.user,
                defaults={'is_active': True}
            )
            
            # Mark messages as read
            participant.mark_as_read(message)
            return True
            
        except (ChatRoom.DoesNotExist, ChatMessage.DoesNotExist) as e:
            logger.error(f"Error marking messages as read: {e}")
            return False
    
    async def send_error(self, message):
        """Send error message to WebSocket"""
        await self.send(text_data=json.dumps({
            'type': 'error',
            'message': message,
            'timestamp': timezone.now().isoformat()
        }))


# Additional Consumer for System-wide Notifications
class NotificationConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for system-wide notifications"""
    
    async def connect(self):
        """Handle WebSocket connection for notifications"""
        self.user = self.scope.get('user')
        
        if not self.user or not self.user.is_authenticated:
            await self.close(code=4001)
            return
        
        self.user_group_name = f'user_{self.user.id}'
        
        # Join user-specific notification group
        await self.channel_layer.group_add(
            self.user_group_name,
            self.channel_name
        )
        
        await self.accept()
        logger.info(f"User {self.user.email} connected to notifications")
    
    async def disconnect(self, close_code):
        """Handle WebSocket disconnection"""
        if hasattr(self, 'user_group_name'):
            await self.channel_layer.group_discard(
                self.user_group_name,
                self.channel_name
            )
            logger.info(f"User {self.user.email} disconnected from notifications")
    
    async def receive(self, text_data):
        """Handle messages from WebSocket"""
        try:
            data = json.loads(text_data)
            message_type = data.get('type')
            
            if message_type == 'ping':
                await self.send(text_data=json.dumps({
                    'type': 'pong',
                    'timestamp': timezone.now().isoformat()
                }))
        except json.JSONDecodeError:
            pass
    
    # Event handlers for different notification types
    async def system_notification(self, event):
        """Send system notification to WebSocket"""
        await self.send(text_data=json.dumps({
            'type': 'system_notification',
            'title': event['title'],
            'message': event['message'],
            'level': event.get('level', 'info'),
            'timestamp': event.get('timestamp')
        }))
    
    async def request_notification(self, event):
        """Send request-related notification to WebSocket"""
        await self.send(text_data=json.dumps({
            'type': 'request_notification',
            'action': event['action'],
            'request_id': event['request_id'],
            'title': event['title'],
            'message': event['message'],
            'timestamp': event.get('timestamp')
        }))
    
    async def assignment_notification(self, event):
        """Send assignment notification to WebSocket"""
        await self.send(text_data=json.dumps({
            'type': 'assignment_notification',
            'action': event['action'],
            'request_id': event['request_id'],
            'request_title': event['request_title'],
            'assigned_by': event['assigned_by'],
            'timestamp': event.get('timestamp')
        }))