# apps/chat/models.py
import uuid
from django.db import models
from django.conf import settings
from django.utils import timezone
from django.core.exceptions import ValidationError


class ChatRoom(models.Model):
    """Chat room for each service request"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    request = models.OneToOneField(
        'service_requests.ServiceRequest',
        on_delete=models.CASCADE,
        related_name='chat_room'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    
    # Room settings
    allow_file_sharing = models.BooleanField(default=True)
    max_file_size = models.PositiveIntegerField(default=52428800)  # 50MB
    
    class Meta:
        db_table = 'chat_rooms'
        verbose_name = 'Chat Room'
        verbose_name_plural = 'Chat Rooms'
    
    def __str__(self):
        return f"Chat for {self.request.title}"
    
    def get_participants(self):
        """Get all participants in this chat room"""
        participants = [self.request.client]
        if self.request.accountant:
            participants.append(self.request.accountant)
        
        # Add any admin users who have sent messages
        admin_participants = ChatMessage.objects.filter(
            room=self,
            sender__role='admin'
        ).values_list('sender', flat=True).distinct()
        
        admin_users = settings.AUTH_USER_MODEL.objects.filter(
            id__in=admin_participants
        )
        participants.extend(admin_users)
        
        return list(set(participants))
    
    def can_user_access(self, user):
        """Check if user can access this chat room"""
        if user.role == 'admin':
            return True
        elif user.role == 'client':
            return self.request.client == user
        elif user.role == 'accountant':
            return self.request.accountant == user
        return False
    
    def get_unread_count(self, user):
        """Get unread message count for a user"""
        return self.messages.filter(
            is_read=False
        ).exclude(sender=user).count()


class ChatMessage(models.Model):
    """Individual chat messages"""
    MESSAGE_TYPES = [
        ('text', 'Text Message'),
        ('file', 'File Message'),
        ('system', 'System Message'),
        ('image', 'Image Message'),
        ('document', 'Document Message'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    room = models.ForeignKey(
        ChatRoom,
        on_delete=models.CASCADE,
        related_name='messages'
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='sent_messages'
    )
    message_type = models.CharField(
        max_length=20,
        choices=MESSAGE_TYPES,
        default='text'
    )
    content = models.TextField()
    
    # File-related fields
    file = models.ForeignKey(
        'file_management.File',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='chat_messages'
    )
    
    # Message status
    is_read = models.BooleanField(default=False)
    is_deleted = models.BooleanField(default=False)
    is_edited = models.BooleanField(default=False)
    
    # Metadata
    metadata = models.JSONField(default=dict, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    edited_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'chat_messages'
        verbose_name = 'Chat Message'
        verbose_name_plural = 'Chat Messages'
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['room', 'created_at']),
            models.Index(fields=['sender', 'created_at']),
            models.Index(fields=['room', 'is_read']),
        ]
    
    def __str__(self):
        return f"{self.sender.full_name}: {self.content[:50]}"
    
    def clean(self):
        if self.message_type == 'file' and not self.file:
            raise ValidationError('File is required for file messages')
        if self.message_type in ['text', 'system'] and self.file:
            raise ValidationError('File should not be provided for text/system messages')
    
    def save(self, *args, **kwargs):
        self.clean()
        if self.pk and self.is_edited:
            self.edited_at = timezone.now()
        super().save(*args, **kwargs)
    
    def can_user_edit(self, user):
        """Check if user can edit this message"""
        if self.message_type == 'system':
            return False
        return self.sender == user and self.created_at > timezone.now() - timezone.timedelta(minutes=15)
    
    def can_user_delete(self, user):
        """Check if user can delete this message"""
        if self.message_type == 'system':
            return False
        return self.sender == user or user.role == 'admin'


class MessageReaction(models.Model):
    """Message reactions/emojis"""
    EMOJI_CHOICES = [
        ('👍', 'Thumbs Up'),
        ('👎', 'Thumbs Down'),
        ('❤️', 'Heart'),
        ('😂', 'Laughing'),
        ('😮', 'Surprised'),
        ('😢', 'Sad'),
        ('😡', 'Angry'),
        ('✅', 'Check Mark'),
        ('❌', 'Cross Mark'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    message = models.ForeignKey(
        ChatMessage,
        on_delete=models.CASCADE,
        related_name='reactions'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='message_reactions'
    )
    emoji = models.CharField(max_length=10, choices=EMOJI_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'message_reactions'
        verbose_name = 'Message Reaction'
        verbose_name_plural = 'Message Reactions'
        unique_together = ['message', 'user', 'emoji']
        indexes = [
            models.Index(fields=['message', 'emoji']),
        ]
    
    def __str__(self):
        return f"{self.user.full_name} reacted {self.emoji} to message"


class ChatParticipant(models.Model):
    """Track chat participants and their status"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    room = models.ForeignKey(
        ChatRoom,
        on_delete=models.CASCADE,
        related_name='participants'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='chat_participations'
    )
    
    # Participation status
    is_active = models.BooleanField(default=True)
    is_muted = models.BooleanField(default=False)
    
    # Activity tracking
    last_read_message = models.ForeignKey(
        ChatMessage,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='last_read_by'
    )
    last_seen = models.DateTimeField(default=timezone.now)
    joined_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'chat_participants'
        verbose_name = 'Chat Participant'
        verbose_name_plural = 'Chat Participants'
        unique_together = ['room', 'user']
        indexes = [
            models.Index(fields=['room', 'is_active']),
            models.Index(fields=['user', 'last_seen']),
        ]
    
    def __str__(self):
        return f"{self.user.full_name} in {self.room}"
    
    def mark_as_read(self, message):
        """Mark messages as read up to the specified message"""
        self.last_read_message = message
        self.last_seen = timezone.now()
        self.save(update_fields=['last_read_message', 'last_seen'])
        
        # Mark all previous messages as read
        ChatMessage.objects.filter(
            room=self.room,
            created_at__lte=message.created_at
        ).exclude(sender=self.user).update(is_read=True)
    
    def get_unread_count(self):
        """Get count of unread messages"""
        if not self.last_read_message:
            return self.room.messages.exclude(sender=self.user).count()
        
        return self.room.messages.filter(
            created_at__gt=self.last_read_message.created_at
        ).exclude(sender=self.user).count()


class TypingIndicator(models.Model):
    """Track who is currently typing"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    room = models.ForeignKey(
        ChatRoom,
        on_delete=models.CASCADE,
        related_name='typing_indicators'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='typing_in_rooms'
    )
    is_typing = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'typing_indicators'
        verbose_name = 'Typing Indicator'
        verbose_name_plural = 'Typing Indicators'
        unique_together = ['room', 'user']
        indexes = [
            models.Index(fields=['room', 'is_typing']),
            models.Index(fields=['updated_at']),
        ]
    
    def __str__(self):
        return f"{self.user.full_name} typing in {self.room}"
    
    @classmethod
    def cleanup_old_indicators(cls, minutes=5):
        """Remove old typing indicators"""
        cutoff = timezone.now() - timezone.timedelta(minutes=minutes)
        cls.objects.filter(updated_at__lt=cutoff).delete()


class MessageThread(models.Model):
    """Message threads for replies"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    parent_message = models.ForeignKey(
        ChatMessage,
        on_delete=models.CASCADE,
        related_name='thread'
    )
    reply_message = models.ForeignKey(
        ChatMessage,
        on_delete=models.CASCADE,
        related_name='reply_to'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'message_threads'
        verbose_name = 'Message Thread'
        verbose_name_plural = 'Message Threads'
        unique_together = ['parent_message', 'reply_message']
        indexes = [
            models.Index(fields=['parent_message', 'created_at']),
        ]
    
    def __str__(self):
        return f"Reply to {self.parent_message.id}"


class ChatSettings(models.Model):
    """Chat settings for users"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='chat_settings'
    )
    
    # Notification settings
    email_notifications = models.BooleanField(default=True)
    push_notifications = models.BooleanField(default=True)
    desktop_notifications = models.BooleanField(default=True)
    sound_notifications = models.BooleanField(default=True)
    
    # Chat preferences
    show_typing_indicators = models.BooleanField(default=True)
    show_read_receipts = models.BooleanField(default=True)
    auto_download_files = models.BooleanField(default=False)
    theme = models.CharField(
        max_length=20,
        choices=[('light', 'Light'), ('dark', 'Dark')],
        default='light'
    )
    
    # Privacy settings
    allow_direct_messages = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'chat_settings'
        verbose_name = 'Chat Settings'
        verbose_name_plural = 'Chat Settings'
    
    def __str__(self):
        return f"Chat settings for {self.user.full_name}"