# apps/chat/tasks.py
from celery import shared_task
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings
from django.utils import timezone
from datetime import timedelta
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
import logging

from .models import ChatMessage, TypingIndicator, ChatRoom, ChatParticipant
# from apps.notifications.models import Notification
from django.contrib.auth import get_user_model

logger = logging.getLogger(__name__)
User = get_user_model()


@shared_task(bind=True, max_retries=3)
def send_new_message_notification(self, message_id, recipient_user_ids):
    """Send email notification for new chat messages"""
    try:
        message = ChatMessage.objects.select_related(
            'sender', 'room', 'room__request'
        ).get(id=message_id)
        
        recipients = User.objects.filter(
            id__in=recipient_user_ids,
            chat_settings__email_notifications=True
        )
        
        for recipient in recipients:
            # Don't send notification to message sender
            if recipient.id == message.sender.id:
                continue
            
            # Prepare email context
            context = {
                'recipient': recipient,
                'sender': message.sender,
                'message': message,
                'request': message.room.request,
                'chat_url': f"{settings.FRONTEND_URL}/requests/{message.room.request.id}/chat"
            }
            
            # Render email templates
            subject = f"New message from {message.sender.full_name}"
            html_message = render_to_string('emails/new_chat_message.html', context)
            text_message = render_to_string('emails/new_chat_message.txt', context)
            
            # Send email
            send_mail(
                subject=subject,
                message=text_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[recipient.email],
                html_message=html_message,
                fail_silently=False
            )
            
            logger.info(f"Sent new message notification to {recipient.email}")
    
    except ChatMessage.DoesNotExist:
        logger.error(f"Message {message_id} not found for notification")
    except Exception as exc:
        logger.error(f"Error sending message notification: {exc}")
        if self.request.retries < self.max_retries:
            raise self.retry(countdown=60 * (2 ** self.request.retries))


@shared_task
def cleanup_old_typing_indicators():
    """Remove typing indicators older than 5 minutes"""
    try:
        cutoff = timezone.now() - timedelta(minutes=5)
        deleted_count = TypingIndicator.objects.filter(
            updated_at__lt=cutoff
        ).delete()[0]
        
        logger.info(f"Cleaned up {deleted_count} old typing indicators")
        return deleted_count
    except Exception as exc:
        logger.error(f"Error cleaning up typing indicators: {exc}")
        return 0


@shared_task
def cleanup_inactive_chat_participants():
    """Clean up participants who haven't been seen for 30 days"""
    try:
        cutoff = timezone.now() - timedelta(days=30)
        deleted_count = ChatParticipant.objects.filter(
            last_seen__lt=cutoff,
            is_active=False
        ).delete()[0]
        
        logger.info(f"Cleaned up {deleted_count} inactive chat participants")
        return deleted_count
    except Exception as exc:
        logger.error(f"Error cleaning up chat participants: {exc}")
        return 0


@shared_task
def generate_chat_summary_report():
    """Generate daily chat activity summary"""
    try:
        yesterday = timezone.now() - timedelta(days=1)
        start_of_day = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = yesterday.replace(hour=23, minute=59, second=59, microsecond=999999)
        
        # Get chat statistics for yesterday
        total_messages = ChatMessage.objects.filter(
            created_at__range=[start_of_day, end_of_day],
            is_deleted=False
        ).count()
        
        active_rooms = ChatRoom.objects.filter(
            messages__created_at__range=[start_of_day, end_of_day],
            messages__is_deleted=False
        ).distinct().count()
        
        active_users = User.objects.filter(
            sent_messages__created_at__range=[start_of_day, end_of_day],
            sent_messages__is_deleted=False
        ).distinct().count()
        
        # Send summary to admins
        admins = User.objects.filter(role='admin', is_active=True)
        
        context = {
            'date': yesterday.date(),
            'total_messages': total_messages,
            'active_rooms': active_rooms,
            'active_users': active_users
        }
        
        subject = f"Daily Chat Summary - {yesterday.date()}"
        html_message = render_to_string('emails/chat_summary_report.html', context)
        text_message = render_to_string('emails/chat_summary_report.txt', context)
        
        for admin in admins:
            send_mail(
                subject=subject,
                message=text_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[admin.email],
                html_message=html_message,
                fail_silently=True
            )
        
        logger.info(f"Sent daily chat summary to {admins.count()} admins")
        return context
        
    except Exception as exc:
        logger.error(f"Error generating chat summary report: {exc}")
        return None


@shared_task(bind=True, max_retries=3)
def export_chat_messages(self, room_id, user_id, export_format='json'):
    """Export chat messages for a room"""
    try:
        room = ChatRoom.objects.select_related('request').get(id=room_id)
        user = User.objects.get(id=user_id)
        
        # Check permissions
        if not room.can_user_access(user):
            logger.error(f"User {user_id} doesn't have access to room {room_id}")
            return
        
        messages = ChatMessage.objects.filter(
            room=room,
            is_deleted=False
        ).select_related('sender', 'file').order_by('created_at')
        
        if export_format == 'json':
            # Export as JSON
            from .serializers import ChatMessageSerializer
            serialized_messages = ChatMessageSerializer(
                messages,
                many=True,
                context={'request': type('obj', (object,), {'user': user})()}
            ).data
            
            export_data = {
                'room_info': {
                    'id': str(room.id),
                    'request_title': room.request.title,
                    'export_date': timezone.now().isoformat(),
                    'exported_by': user.full_name
                },
                'messages': serialized_messages
            }
            
            # Save to file and send email with download link
            # This would typically use cloud storage
            # For now, just log the success
            logger.info(f"Chat export completed for room {room_id}")
            
            # Notify user via WebSocket
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                f'user_{user_id}',
                {
                    'type': 'system_notification',
                    'title': 'Chat Export Ready',
                    'message': f'Your chat export for "{room.request.title}" is ready for download.',
                    'level': 'success',
                    'timestamp': timezone.now().isoformat()
                }
            )
            
    except (ChatRoom.DoesNotExist, User.DoesNotExist) as exc:
        logger.error(f"Export failed - object not found: {exc}")
    except Exception as exc:
        logger.error(f"Error exporting chat messages: {exc}")
        if self.request.retries < self.max_retries:
            raise self.retry(countdown=60 * (2 ** self.request.retries))


@shared_task
def broadcast_system_notification(title, message, user_ids=None, level='info'):
    """Broadcast system notification to users"""
    try:
        channel_layer = get_channel_layer()
        
        if user_ids:
            # Send to specific users
            for user_id in user_ids:
                async_to_sync(channel_layer.group_send)(
                    f'user_{user_id}',
                    {
                        'type': 'system_notification',
                        'title': title,
                        'message': message,
                        'level': level,
                        'timestamp': timezone.now().isoformat()
                    }
                )
        else:
            # Broadcast to all connected users
            # This would require a different approach in production
            # For now, we'll just log it
            logger.info(f"System broadcast: {title} - {message}")
            
    except Exception as exc:
        logger.error(f"Error broadcasting system notification: {exc}")