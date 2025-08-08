# apps/chat/signals.py
from django.db.models.signals import post_save, post_delete, pre_delete
from django.dispatch import receiver
from django.utils import timezone
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

from .models import ChatMessage, MessageReaction, ChatRoom
from .tasks import send_new_message_notification
from apps.service_requests.models import ServiceRequest
import logging

logger = logging.getLogger(__name__)


@receiver(post_save, sender=ServiceRequest)
def create_chat_room(sender, instance, created, **kwargs):
    """Automatically create a chat room when a service request is created"""
    if created:
        try:
            chat_room = ChatRoom.objects.create(
                request=instance,
                allow_file_sharing=True,
                max_file_size=52428800  # 50MB
            )
            logger.info(f"Created chat room {chat_room.id} for request {instance.id}")
        except Exception as e:
            logger.error(f"Error creating chat room for request {instance.id}: {e}")


@receiver(post_save, sender=ChatMessage)
def handle_new_message(sender, instance, created, **kwargs):
    """Handle new chat message creation"""
    if created and not instance.is_deleted:
        # Get all participants except the sender
        participants = instance.room.get_participants()
        recipient_ids = [
            p.id for p in participants 
            if p.id != instance.sender.id and p.is_active
        ]
        
        if recipient_ids:
            # Send email notifications asynchronously
            send_new_message_notification.delay(
                str(instance.id),
                [str(uid) for uid in recipient_ids]
            )
        
        # Update room's last activity
        instance.room.updated_at = timezone.now()
        instance.room.save(update_fields=['updated_at'])


@receiver(post_save, sender=MessageReaction)
def handle_message_reaction(sender, instance, created, **kwargs):
    """Handle message reaction events"""
    if created:
        # Broadcast reaction to WebSocket consumers
        channel_layer = get_channel_layer()
        room_group_name = f'chat_{instance.message.room.id}'
        
        async_to_sync(channel_layer.group_send)(
            room_group_name,
            {
                'type': 'message_reaction',
                'action': 'reaction_added',
                'message_id': str(instance.message.id),
                'reaction': {
                    'id': str(instance.id),
                    'emoji': instance.emoji,
                    'user': {
                        'id': str(instance.user.id),
                        'full_name': instance.user.full_name
                    }
                }
            }
        )


@receiver(pre_delete, sender=MessageReaction)
def handle_reaction_deletion(sender, instance, **kwargs):
    """Handle message reaction deletion"""
    # Broadcast reaction removal to WebSocket consumers
    channel_layer = get_channel_layer()
    room_group_name = f'chat_{instance.message.room.id}'
    
    async_to_sync(channel_layer.group_send)(
        room_group_name,
        {
            'type': 'message_reaction',
            'action': 'reaction_removed',
            'message_id': str(instance.message.id),
            'emoji': instance.emoji,
            'user_id': str(instance.user.id)
        }
    )


@receiver(post_save, sender=ChatMessage)
def update_read_status(sender, instance, **kwargs):
    """Update read status for message participants"""
    if not kwargs.get('created', False):
        return
    
    # Mark message as read for sender
    try:
        participant = instance.room.participants.get(user=instance.sender)
        participant.last_read_message = instance
        participant.last_seen = timezone.now()
        participant.save(update_fields=['last_read_message', 'last_seen'])
    except:
        pass  # Participant might not exist yet