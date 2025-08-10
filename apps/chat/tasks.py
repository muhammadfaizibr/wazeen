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
from .serializers import ChatMessageExportSerializer
from django.core.files.base import ContentFile
import json
import csv
from io import StringIO
from django.core.files.storage import default_storage


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
            if recipient.id == message.sender.id:
                continue
            
            context = {
                'recipient': recipient,
                'sender': message.sender,
                'message': message,
                'request': message.room.request,
                'chat_url': f"{settings.FRONTEND_URL}/requests/{message.room.request.id}/chat"
            }
            
            # Updated template paths
            subject = f"New message from {message.sender.full_name}"
            html_message = render_to_string('chat/emails/new_chat_message.html', context)
            text_message = render_to_string('chat/emails/new_chat_message.txt', context)
            
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
        # Updated template paths
        html_message = render_to_string('chat/emails/chat_summary_report.html', context)
        text_message = render_to_string('chat/emails/chat_summary_report.txt', context)
        
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
    
def send_export_notification(user_id, room, filename, status_type, error_message=None):
    """Send WebSocket notification about export status"""
    try:
        channel_layer = get_channel_layer()
        
        if status_type == 'success':
            message = f'Your chat export for "{room.request.title}" is ready for download.'
            title = 'Chat Export Ready'
        else:
            message = f'Chat export failed: {error_message}'
            title = 'Chat Export Failed'
        
        async_to_sync(channel_layer.group_send)(
            f'user_{user_id}',
            {
                'type': 'system_notification',
                'title': title,
                'message': message,
                'level': status_type,
                'timestamp': timezone.now().isoformat(),
                'data': {
                    'filename': filename,
                    'download_url': f'/api/chat/export/download/{filename}' if filename else None
                }
            }
        )
    except Exception as e:
        logger.error(f"Failed to send export notification: {e}")

def send_export_email_notification(user, room, filename):
    """Send email notification about completed export"""
    try:
        # Create download URL
        download_url = f"{settings.FRONTEND_URL}/chat/export/download/{filename}"
        
        # Email context
        context = {
            'user': user,
            'room': room,
            'filename': filename,
            'download_url': download_url,
            'export_date': timezone.now(),
            'site_name': getattr(settings, 'SITE_NAME', 'Chat System')
        }
        
        # Use consistent app-specific template paths
        try:
            html_message = render_to_string('chat/emails/export_ready.html', context)
            plain_message = render_to_string('chat/emails/export_ready.txt', context)
            logger.info(f"Using chat/emails/export_ready.html template")
        except Exception as template_error:
            logger.error(f"Template chat/emails/export_ready.html not found: {template_error}")
            # Fallback to plain text only if templates don't exist
            plain_message = f"""
Hello {user.full_name},

Your chat export for "{room.request.title}" is ready for download.

Filename: {filename}
Export Date: {timezone.now().strftime('%Y-%m-%d %H:%M:%S')}

You can download your export file by logging into your account and visiting the chat room.

This download link will expire in 7 days.

Best regards,
{getattr(settings, 'SITE_NAME', 'Chat System')} Team
            """.strip()
            
            html_message = None  # No HTML if template fails
        
        # Send email
        send_mail(
            subject=f'Chat Export Ready - {room.request.title}',
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            html_message=html_message,
            fail_silently=False
        )
        
        logger.info(f"Export email sent to {user.email} for room {room.id}")
        
    except Exception as e:
        logger.error(f"Failed to send export email to {user.email}: {e}")
        try:
            send_export_notification(user.id, room, filename, 'error', f'Email notification failed: {str(e)}')
        except:
            pass

def send_export_error_email(user, room, error_message):
    """Send email notification about failed export"""
    try:
        plain_message = f"""
Hello {user.full_name},

Unfortunately, your chat export request for "{room.request.title if room else 'Unknown Room'}" has failed.

Error: {error_message}

Please try again or contact support if the problem persists.

Best regards,
{getattr(settings, 'SITE_NAME', 'Chat System')} Team
        """.strip()
        
        send_mail(
            subject='Chat Export Failed',
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False
        )
        
        logger.info(f"Export error email sent to {user.email}")
        
    except Exception as e:
        logger.error(f"Failed to send export error email to {user.email}: {e}")


@shared_task(bind=True, max_retries=3)
def export_chat_messages(self, room_id, user_id, export_format='json', date_from=None, date_to=None):
    """Export chat messages for a room"""
    try:
        room = ChatRoom.objects.select_related('request').get(id=room_id)
        user = User.objects.get(id=user_id)
        
        # Check permissions
        if not room.can_user_access(user):
            logger.error(f"User {user_id} doesn't have access to room {room_id}")
            send_export_error_email(user, room, "Access denied")
            return
        
        # Build queryset with filters
        messages_qs = ChatMessage.objects.filter(
            room=room,
            is_deleted=False
        ).select_related('sender', 'file').prefetch_related('reactions', 'reactions__user')
        
        # Apply date filters if provided
        if date_from:
            try:
                date_from_parsed = timezone.datetime.fromisoformat(date_from.replace('Z', '+00:00'))
                messages_qs = messages_qs.filter(created_at__gte=date_from_parsed)
            except ValueError:
                logger.warning(f"Invalid date_from format: {date_from}")
        
        if date_to:
            try:
                date_to_parsed = timezone.datetime.fromisoformat(date_to.replace('Z', '+00:00'))
                messages_qs = messages_qs.filter(created_at__lte=date_to_parsed)
            except ValueError:
                logger.warning(f"Invalid date_to format: {date_to}")
        
        messages = messages_qs.order_by('created_at')
        
        # Generate filename
        timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
        safe_title = "".join(c for c in room.request.title if c.isalnum() or c in (' ', '-', '_')).strip()
        safe_title = safe_title[:50]  # Limit length
        filename = f"chat_export_{timestamp}.{export_format}"
        
        # Export based on format
        if export_format == 'json':
            file_content = export_as_json(room, messages, user)
        elif export_format == 'csv':
            file_content = export_as_csv(room, messages, user)
        elif export_format == 'txt':
            file_content = export_as_txt(room, messages, user)
        else:
            raise ValueError(f"Unsupported export format: {export_format}")
        
        # Save file to storage
        file_path = f'chat_exports/{user_id}/{filename}'
        default_storage.save(file_path, ContentFile(file_content.encode('utf-8')))
        
        logger.info(f"Chat export completed for room {room_id}, format {export_format}")
        
        # Send notification via WebSocket
        send_export_notification(user_id, room, filename, 'success')
        
        # Send email notification
        send_export_email_notification(user, room, filename)
        
        return {
            'status': 'completed',
            'filename': filename,
            'message_count': messages.count()
        }
        
    except (ChatRoom.DoesNotExist, User.DoesNotExist) as exc:
        logger.error(f"Export failed - object not found: {exc}")
        try:
            user = User.objects.get(id=user_id) if 'user_id' in locals() else None
            room = ChatRoom.objects.get(id=room_id) if 'room_id' in locals() else None
        except:
            user = None
            room = None
        
        send_export_notification(user_id, room, None, 'error', 'Object not found')
        if user:
            send_export_error_email(user, room, 'Object not found')
        
    except Exception as exc:
        logger.error(f"Error exporting chat messages: {exc}")
        try:
            user = User.objects.get(id=user_id)
            room = ChatRoom.objects.get(id=room_id)
        except:
            user = None
            room = None
            
        send_export_notification(user_id, room, None, 'error', str(exc))
        if user:
            send_export_error_email(user, room, str(exc))
        
        if self.request.retries < self.max_retries:
            raise self.retry(countdown=60 * (2 ** self.request.retries))


def export_as_json(room, messages, user):
    """Export messages as JSON"""
    serialized_messages = ChatMessageExportSerializer(
        messages,
        many=True,
        context={'request': type('obj', (object,), {'user': user})()}
    ).data
    
    export_data = {
        'room_info': {
            'id': str(room.id),
            'request_title': room.request.title,
            'request_id': str(room.request.id),
            'export_date': timezone.now().isoformat(),
            'exported_by': user.full_name,
            'message_count': len(serialized_messages)
        },
        'messages': serialized_messages
    }
    
    return json.dumps(export_data, indent=2, ensure_ascii=False)


def export_as_csv(room, messages, user):
    """Export messages as CSV"""
    output = StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow([
        'Timestamp',
        'Sender',
        'Sender Role',
        'Message Type',
        'Content',
        'File Name',
        'Reactions',
        'Is Edited'
    ])
    
    # Write messages
    for message in messages:
        reactions = ', '.join([
            f"{r.emoji} ({r.user.full_name})" 
            for r in message.reactions.all()
        ])
        
        writer.writerow([
            message.created_at.isoformat(),
            message.sender.full_name,
            message.sender.get_role_display() if hasattr(message.sender, 'get_role_display') else message.sender.role,
            message.get_message_type_display(),
            message.content,
            message.file.filename if message.file else '',
            reactions,
            'Yes' if message.is_edited else 'No'
        ])
    
    # Add metadata at the top
    csv_content = f"# Chat Export for: {room.request.title}\n"
    csv_content += f"# Exported by: {user.full_name}\n"
    csv_content += f"# Export date: {timezone.now().isoformat()}\n"
    csv_content += f"# Message count: {messages.count()}\n\n"
    csv_content += output.getvalue()
    
    return csv_content


def export_as_txt(room, messages, user):
    """Export messages as plain text"""
    lines = []
    lines.append(f"Chat Export: {room.request.title}")
    lines.append(f"Exported by: {user.full_name}")
    lines.append(f"Export date: {timezone.now().isoformat()}")
    lines.append(f"Message count: {messages.count()}")
    lines.append("=" * 50)
    lines.append("")
    
    for message in messages:
        timestamp = message.created_at.strftime('%Y-%m-%d %H:%M:%S')
        sender = message.sender.full_name
        
        # Message header
        header = f"[{timestamp}] {sender}"
        if message.is_edited:
            header += " (edited)"
        lines.append(header)
        
        # Message content
        if message.message_type == 'system':
            lines.append(f"SYSTEM: {message.content}")
        elif message.message_type in ['file', 'image', 'document']:
            lines.append(f"FILE: {message.file.filename if message.file else 'Unknown file'}")
            if message.content.strip():
                lines.append(f"Caption: {message.content}")
        else:
            lines.append(message.content)
        
        # Reactions
        reactions = message.reactions.all()
        if reactions:
            reaction_text = "Reactions: " + ", ".join([
                f"{r.emoji} ({r.user.full_name})" for r in reactions
            ])
            lines.append(reaction_text)
        
        lines.append("")  # Empty line between messages
    
    return "\n".join(lines)

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