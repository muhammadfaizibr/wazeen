# apps/chat/serializers.py
from rest_framework import serializers
from django.utils import timezone
from django.contrib.auth import get_user_model
from apps.file_management.serializers import FileListSerializer
from .models import (
    ChatRoom, ChatMessage, MessageReaction, ChatParticipant,
    TypingIndicator, MessageThread, ChatSettings
)

User = get_user_model()


class UserBasicSerializer(serializers.ModelSerializer):
    """Basic user info for chat"""
    class Meta:
        model = User
        fields = ['id', 'full_name', 'role', 'avatar']


class MessageReactionSerializer(serializers.ModelSerializer):
    """Serializer for message reactions"""
    user = UserBasicSerializer(read_only=True)
    
    class Meta:
        model = MessageReaction
        fields = ['id', 'user', 'emoji', 'created_at']
        read_only_fields = ['id', 'user', 'created_at']


class MessageReactionCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating message reactions"""
    class Meta:
        model = MessageReaction
        fields = ['emoji']
    
    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user
        validated_data['message'] = self.context['message']
        
        # Remove existing reaction with same emoji from same user
        MessageReaction.objects.filter(
            message=validated_data['message'],
            user=validated_data['user'],
            emoji=validated_data['emoji']
        ).delete()
        
        return super().create(validated_data)


class MessageThreadSerializer(serializers.ModelSerializer):
    """Serializer for message threads"""
    parent_message_preview = serializers.SerializerMethodField()
    
    class Meta:
        model = MessageThread
        fields = ['id', 'parent_message', 'parent_message_preview', 'created_at']
        read_only_fields = ['id', 'created_at']
    
    def get_parent_message_preview(self, obj):
        return {
            'id': obj.parent_message.id,
            'content': obj.parent_message.content[:100],
            'sender': obj.parent_message.sender.full_name,
            'created_at': obj.parent_message.created_at
        }


class ChatMessageSerializer(serializers.ModelSerializer):
    """Detailed chat message serializer"""
    sender = UserBasicSerializer(read_only=True)
    file = FileListSerializer(read_only=True)
    reactions = MessageReactionSerializer(many=True, read_only=True)
    reaction_summary = serializers.SerializerMethodField()
    thread_count = serializers.SerializerMethodField()
    parent_message = serializers.SerializerMethodField()
    can_edit = serializers.SerializerMethodField()
    can_delete = serializers.SerializerMethodField()
    
    class Meta:
        model = ChatMessage
        fields = [
            'id', 'sender', 'message_type', 'content', 'file',
            'is_read', 'is_deleted', 'is_edited', 'metadata',
            'created_at', 'updated_at', 'edited_at',
            'reactions', 'reaction_summary', 'thread_count',
            'parent_message', 'can_edit', 'can_delete'
        ]
        read_only_fields = [
            'id', 'sender', 'is_read', 'is_deleted', 'is_edited',
            'created_at', 'updated_at', 'edited_at'
        ]
    
    def get_reaction_summary(self, obj):
        """Get summary of reactions grouped by emoji"""
        reactions = obj.reactions.all()
        summary = {}
        for reaction in reactions:
            emoji = reaction.emoji
            if emoji not in summary:
                summary[emoji] = {
                    'count': 0,
                    'users': []
                }
            summary[emoji]['count'] += 1
            summary[emoji]['users'].append({
                'id': str(reaction.user.id),
                'name': reaction.user.full_name
            })
        return summary
    
    def get_thread_count(self, obj):
        """Get count of thread replies"""
        return obj.thread.count()
    
    def get_parent_message(self, obj):
        """Get parent message if this is a reply"""
        if obj.reply_to.exists():
            parent = obj.reply_to.first().parent_message
            return {
                'id': str(parent.id),
                'content': parent.content[:100],
                'sender': parent.sender.full_name,
                'created_at': parent.created_at
            }
        return None
    
    def get_can_edit(self, obj):
        """Check if current user can edit this message"""
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return False
        return obj.can_user_edit(request.user)
    
    def get_can_delete(self, obj):
        """Check if current user can delete this message"""
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return False
        return obj.can_user_delete(request.user)


class ChatMessageListSerializer(serializers.ModelSerializer):
    """Simplified message serializer for list views"""
    sender = UserBasicSerializer(read_only=True)
    file_name = serializers.CharField(source='file.original_filename', read_only=True)
    reaction_count = serializers.SerializerMethodField()
    
    class Meta:
        model = ChatMessage
        fields = [
            'id', 'sender', 'message_type', 'content', 'file_name',
            'is_read', 'is_edited', 'created_at', 'reaction_count'
        ]
    
    def get_reaction_count(self, obj):
        return obj.reactions.count()


class ChatMessageCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating chat messages"""
    file_id = serializers.UUIDField(required=False, allow_null=True, write_only=True)
    parent_message_id = serializers.UUIDField(required=False, allow_null=True, write_only=True)
    
    class Meta:
        model = ChatMessage
        fields = [
            'message_type', 'content', 'file_id', 'parent_message_id', 'metadata'
        ]
    
    def validate(self, attrs):
        message_type = attrs.get('message_type', 'text')
        file_id = attrs.get('file_id')
        content = attrs.get('content', '').strip()
        
        # Validate content based on message type
        if message_type in ['text', 'system'] and not content:
            raise serializers.ValidationError('Content is required for text messages')
        
        if message_type in ['file', 'image', 'document'] and not file_id:
            raise serializers.ValidationError('File is required for file messages')
        
        return attrs
    
    def create(self, validated_data):
        file_id = validated_data.pop('file_id', None)
        parent_message_id = validated_data.pop('parent_message_id', None)
        
        # Set room and sender from context
        validated_data['room'] = self.context['room']
        validated_data['sender'] = self.context['request'].user
        
        # Handle file attachment
        if file_id:
            from apps.file_management.models import File
            try:
                file_obj = File.objects.get(id=file_id, is_deleted=False)
                validated_data['file'] = file_obj
                
                # Auto-detect message type based on file
                if not validated_data.get('message_type') or validated_data['message_type'] == 'text':
                    if file_obj.mime_type.startswith('image/'):
                        validated_data['message_type'] = 'image'
                    else:
                        validated_data['message_type'] = 'document'
            except File.DoesNotExist:
                raise serializers.ValidationError('Invalid file ID')
        
        message = super().create(validated_data)
        
        # Handle thread reply
        if parent_message_id:
            try:
                parent_message = ChatMessage.objects.get(
                    id=parent_message_id,
                    room=message.room
                )
                MessageThread.objects.create(
                    parent_message=parent_message,
                    reply_message=message
                )
            except ChatMessage.DoesNotExist:
                pass  # Ignore invalid parent message
        
        return message


class ChatMessageUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating chat messages"""
    class Meta:
        model = ChatMessage
        fields = ['content']
    
    def update(self, instance, validated_data):
        if not instance.can_user_edit(self.context['request'].user):
            raise serializers.ValidationError('Cannot edit this message')
        
        instance.is_edited = True
        return super().update(instance, validated_data)


class ChatParticipantSerializer(serializers.ModelSerializer):
    """Serializer for chat participants"""
    user = UserBasicSerializer(read_only=True)
    unread_count = serializers.SerializerMethodField()
    is_online = serializers.SerializerMethodField()
    
    class Meta:
        model = ChatParticipant
        fields = [
            'id', 'user', 'is_active', 'is_muted', 'last_seen',
            'joined_at', 'unread_count', 'is_online'
        ]
        read_only_fields = ['id', 'user', 'joined_at']
    
    def get_unread_count(self, obj):
        return obj.get_unread_count()
    
    def get_is_online(self, obj):
        # Consider user online if last seen within 5 minutes
        cutoff = timezone.now() - timezone.timedelta(minutes=5)
        return obj.last_seen > cutoff


class TypingIndicatorSerializer(serializers.ModelSerializer):
    """Serializer for typing indicators"""
    user = UserBasicSerializer(read_only=True)
    
    class Meta:
        model = TypingIndicator
        fields = ['id', 'user', 'is_typing', 'updated_at']
        read_only_fields = ['id', 'user', 'updated_at']


class ChatRoomSerializer(serializers.ModelSerializer):
    """Detailed chat room serializer"""
    participants = ChatParticipantSerializer(many=True, read_only=True)
    last_message = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()
    typing_users = serializers.SerializerMethodField()
    request_info = serializers.SerializerMethodField()
    
    class Meta:
        model = ChatRoom
        fields = [
            'id', 'request', 'is_active', 'allow_file_sharing',
            'max_file_size', 'created_at', 'updated_at',
            'participants', 'last_message', 'unread_count',
            'typing_users', 'request_info'
        ]
        read_only_fields = [
            'id', 'request', 'created_at', 'updated_at'
        ]
    
    def get_last_message(self, obj):
        last_message = obj.messages.filter(is_deleted=False).last()
        if last_message:
            return ChatMessageListSerializer(
                last_message,
                context=self.context
            ).data
        return None
    
    def get_unread_count(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.get_unread_count(request.user)
        return 0
    
    def get_typing_users(self, obj):
        # Get users currently typing (updated within last 10 seconds)
        cutoff = timezone.now() - timezone.timedelta(seconds=10)
        typing = obj.typing_indicators.filter(
            is_typing=True,
            updated_at__gte=cutoff
        ).exclude(
            user=self.context.get('request').user if self.context.get('request') else None
        )
        return UserBasicSerializer([t.user for t in typing], many=True).data
    
    def get_request_info(self, obj):
        return {
            'id': str(obj.request.id),
            'title': obj.request.title,
            'status': obj.request.status,
            'client': obj.request.client.full_name,
            'accountant': obj.request.accountant.full_name if obj.request.accountant else None
        }


class ChatRoomListSerializer(serializers.ModelSerializer):
    """Simplified chat room serializer for list views"""
    last_message = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()
    request_title = serializers.CharField(source='request.title', read_only=True)
    request_status = serializers.CharField(source='request.status', read_only=True)
    
    class Meta:
        model = ChatRoom
        fields = [
            'id', 'request', 'request_title', 'request_status',
            'is_active', 'updated_at', 'last_message', 'unread_count'
        ]
    
    def get_last_message(self, obj):
        last_message = obj.messages.filter(is_deleted=False).last()
        if last_message:
            return {
                'content': last_message.content[:100],
                'sender': last_message.sender.full_name,
                'created_at': last_message.created_at,
                'message_type': last_message.message_type
            }
        return None
    
    def get_unread_count(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.get_unread_count(request.user)
        return 0


class ChatSettingsSerializer(serializers.ModelSerializer):
    """Serializer for chat settings"""
    class Meta:
        model = ChatSettings
        fields = [
            'id', 'email_notifications', 'push_notifications',
            'desktop_notifications', 'sound_notifications',
            'show_typing_indicators', 'show_read_receipts',
            'auto_download_files', 'theme', 'allow_direct_messages',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class BulkMarkAsReadSerializer(serializers.Serializer):
    """Serializer for bulk marking messages as read"""
    message_id = serializers.UUIDField()
    
    def validate_message_id(self, value):
        room = self.context['room']
        try:
            message = ChatMessage.objects.get(id=value, room=room)
            return message
        except ChatMessage.DoesNotExist:
            raise serializers.ValidationError('Invalid message ID')


class ChatStatsSerializer(serializers.Serializer):
    """Serializer for chat statistics"""
    total_messages = serializers.IntegerField()
    total_files_shared = serializers.IntegerField()
    active_participants = serializers.IntegerField()
    messages_today = serializers.IntegerField()
    average_response_time = serializers.FloatField()  # in minutes


class ChatMessageExportSerializer(serializers.ModelSerializer):
    """Serializer for exporting chat messages"""
    sender_name = serializers.CharField(source='sender.full_name', read_only=True)
    sender_role = serializers.CharField(source='sender.role', read_only=True)
    file_name = serializers.CharField(source='file.filename', read_only=True)
    file_url = serializers.CharField(source='file.file.url', read_only=True)
    reactions = serializers.SerializerMethodField()
    
    class Meta:
        model = ChatMessage
        fields = [
            'id', 'message_type', 'content', 'sender_name', 'sender_role',
            'file_name', 'file_url', 'is_edited', 'created_at', 'updated_at',
            'reactions'
        ]
    
    def get_reactions(self, obj):
        return [
            {
                'emoji': reaction.emoji,
                'user_name': reaction.user.full_name,
                'created_at': reaction.created_at.isoformat()
            }
            for reaction in obj.reactions.all()
        ]
