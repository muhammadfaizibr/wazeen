# apps/chat/admin.py
from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.urls import reverse
from django.db.models import Count, Q
from django.utils import timezone
from datetime import timedelta

from .models import (
    ChatRoom, ChatMessage, MessageReaction, ChatParticipant,
    TypingIndicator, MessageThread, ChatSettings
)


@admin.register(ChatRoom)
class ChatRoomAdmin(admin.ModelAdmin):
    """Admin interface for ChatRoom"""
    list_display = [
        'id', 'request_title', 'request_client', 'request_accountant',
        'messages_count', 'participants_count', 'is_active', 'created_at'
    ]
    list_filter = [
        'is_active', 'allow_file_sharing', 'created_at',
        'request__status', 'request__priority'
    ]
    search_fields = [
        'request__title', 'request__client__email',
        'request__accountant__email', 'id'
    ]
    readonly_fields = ['id', 'created_at', 'updated_at', 'messages_count', 'participants_count']
    fieldsets = (
        ('Basic Information', {
            'fields': ('id', 'request', 'is_active')
        }),
        ('Room Settings', {
            'fields': ('allow_file_sharing', 'max_file_size')
        }),
        ('Statistics', {
            'fields': ('messages_count', 'participants_count'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    raw_id_fields = ['request']
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'request', 'request__client', 'request__accountant'
        ).annotate(
            messages_count=Count('messages', distinct=True),
            participants_count=Count('participants', distinct=True)
        )
    
    def request_title(self, obj):
        return obj.request.title
    request_title.short_description = 'Request Title'
    request_title.admin_order_field = 'request__title'
    
    def request_client(self, obj):
        if obj.request.client:
            url = reverse('admin:authentication_user_change', args=[obj.request.client.pk])
            return format_html('<a href="{}">{}</a>', url, obj.request.client.email)
        return '-'
    request_client.short_description = 'Client'
    request_client.admin_order_field = 'request__client__email'
    
    def request_accountant(self, obj):
        if obj.request.accountant:
            url = reverse('admin:authentication_user_change', args=[obj.request.accountant.pk])
            return format_html('<a href="{}">{}</a>', url, obj.request.accountant.email)
        return '-'
    request_accountant.short_description = 'Accountant'
    request_accountant.admin_order_field = 'request__accountant__email'
    
    def messages_count(self, obj):
        return getattr(obj, 'messages_count', obj.messages.count())
    messages_count.short_description = 'Messages'
    messages_count.admin_order_field = 'messages_count'
    
    def participants_count(self, obj):
        return getattr(obj, 'participants_count', obj.participants.count())
    participants_count.short_description = 'Participants'
    participants_count.admin_order_field = 'participants_count'


class MessageReactionInline(admin.TabularInline):
    """Inline for message reactions"""
    model = MessageReaction
    extra = 0
    readonly_fields = ['created_at']
    raw_id_fields = ['user']


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    """Admin interface for ChatMessage"""
    list_display = [
        'id', 'room_title', 'sender_email', 'message_type',
        'content_preview', 'has_file', 'is_read', 'is_deleted', 'created_at'
    ]
    list_filter = [
        'message_type', 'is_read', 'is_deleted', 'is_edited',
        'created_at', 'room__request__status'
    ]
    search_fields = [
        'content', 'sender__email', 'room__request__title', 'id'
    ]
    readonly_fields = [
        'id', 'created_at', 'updated_at', 'edited_at',
        'reactions_count', 'content_preview'
    ]
    fieldsets = (
        ('Basic Information', {
            'fields': ('id', 'room', 'sender', 'message_type', 'content')
        }),
        ('File Attachment', {
            'fields': ('file',),
            'classes': ('collapse',)
        }),
        ('Message Status', {
            'fields': ('is_read', 'is_deleted', 'is_edited')
        }),
        ('Metadata', {
            'fields': ('metadata',),
            'classes': ('collapse',)
        }),
        ('Statistics', {
            'fields': ('reactions_count',),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at', 'edited_at'),
            'classes': ('collapse',)
        })
    )
    raw_id_fields = ['room', 'sender', 'file']
    inlines = [MessageReactionInline]
    date_hierarchy = 'created_at'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'room', 'room__request', 'sender', 'file'
        ).annotate(
            reactions_count=Count('reactions', distinct=True)
        )
    
    def room_title(self, obj):
        return obj.room.request.title
    room_title.short_description = 'Room'
    room_title.admin_order_field = 'room__request__title'
    
    def sender_email(self, obj):
        if obj.sender:
            url = reverse('admin:authentication_user_change', args=[obj.sender.pk])
            return format_html('<a href="{}">{}</a>', url, obj.sender.email)
        return '-'
    sender_email.short_description = 'Sender'
    sender_email.admin_order_field = 'sender__email'
    
    def content_preview(self, obj):
        if obj.message_type == 'file':
            return f"[FILE] {obj.file.original_filename if obj.file else 'No file'}"
        elif obj.content:
            preview = obj.content[:100]
            if len(obj.content) > 100:
                preview += "..."
            return preview
        return '-'
    content_preview.short_description = 'Content Preview'
    
    def has_file(self, obj):
        return bool(obj.file)
    has_file.boolean = True
    has_file.short_description = 'Has File'
    
    def reactions_count(self, obj):
        return getattr(obj, 'reactions_count', obj.reactions.count())
    reactions_count.short_description = 'Reactions'
    reactions_count.admin_order_field = 'reactions_count'


@admin.register(MessageReaction)
class MessageReactionAdmin(admin.ModelAdmin):
    """Admin interface for MessageReaction"""
    list_display = ['id', 'message_preview', 'user_email', 'emoji', 'created_at']
    list_filter = ['emoji', 'created_at']
    search_fields = ['user__email', 'message__content', 'id']
    readonly_fields = ['id', 'created_at']
    raw_id_fields = ['message', 'user']
    date_hierarchy = 'created_at'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('message', 'user')
    
    def message_preview(self, obj):
        return obj.message.content[:50] + "..." if len(obj.message.content) > 50 else obj.message.content
    message_preview.short_description = 'Message'
    
    def user_email(self, obj):
        return obj.user.email
    user_email.short_description = 'User'
    user_email.admin_order_field = 'user__email'


@admin.register(ChatParticipant)
class ChatParticipantAdmin(admin.ModelAdmin):
    """Admin interface for ChatParticipant"""
    list_display = [
        'id', 'room_title', 'user_email', 'is_active',
        'is_muted', 'unread_count', 'last_seen', 'joined_at'
    ]
    list_filter = [
        'is_active', 'is_muted', 'last_seen', 'joined_at',
        'room__request__status'
    ]
    search_fields = ['user__email', 'room__request__title', 'id']
    readonly_fields = [
        'id', 'joined_at', 'unread_count', 'last_seen_formatted'
    ]
    fieldsets = (
        ('Basic Information', {
            'fields': ('id', 'room', 'user')
        }),
        ('Status', {
            'fields': ('is_active', 'is_muted')
        }),
        ('Activity', {
            'fields': ('last_read_message', 'last_seen_formatted', 'unread_count')
        }),
        ('Timestamps', {
            'fields': ('joined_at',)
        })
    )
    raw_id_fields = ['room', 'user', 'last_read_message']
    date_hierarchy = 'joined_at'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'room', 'room__request', 'user'
        )
    
    def room_title(self, obj):
        return obj.room.request.title
    room_title.short_description = 'Room'
    room_title.admin_order_field = 'room__request__title'
    
    def user_email(self, obj):
        return obj.user.email
    user_email.short_description = 'User'
    user_email.admin_order_field = 'user__email'
    
    def unread_count(self, obj):
        return obj.get_unread_count()
    unread_count.short_description = 'Unread Messages'
    
    def last_seen_formatted(self, obj):
        if obj.last_seen:
            now = timezone.now()
            diff = now - obj.last_seen
            if diff.days > 0:
                return f"{diff.days} days ago"
            elif diff.seconds > 3600:
                hours = diff.seconds // 3600
                return f"{hours} hours ago"
            elif diff.seconds > 60:
                minutes = diff.seconds // 60
                return f"{minutes} minutes ago"
            else:
                return "Just now"
        return '-'
    last_seen_formatted.short_description = 'Last Seen'


@admin.register(TypingIndicator)
class TypingIndicatorAdmin(admin.ModelAdmin):
    """Admin interface for TypingIndicator"""
    list_display = ['id', 'room_title', 'user_email', 'is_typing', 'updated_at']
    list_filter = ['is_typing', 'updated_at', 'created_at']
    search_fields = ['user__email', 'room__request__title', 'id']
    readonly_fields = ['id', 'created_at', 'updated_at']
    raw_id_fields = ['room', 'user']
    date_hierarchy = 'updated_at'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'room', 'room__request', 'user'
        )
    
    def room_title(self, obj):
        return obj.room.request.title
    room_title.short_description = 'Room'
    room_title.admin_order_field = 'room__request__title'
    
    def user_email(self, obj):
        return obj.user.email
    user_email.short_description = 'User'
    user_email.admin_order_field = 'user__email'
    
    actions = ['cleanup_old_indicators']
    
    def cleanup_old_indicators(self, request, queryset):
        """Remove old typing indicators"""
        cutoff = timezone.now() - timedelta(minutes=5)
        count = TypingIndicator.objects.filter(updated_at__lt=cutoff).delete()[0]
        self.message_user(request, f"Cleaned up {count} old typing indicators.")
    cleanup_old_indicators.short_description = "Clean up old typing indicators"


@admin.register(MessageThread)
class MessageThreadAdmin(admin.ModelAdmin):
    """Admin interface for MessageThread"""
    list_display = [
        'id', 'parent_message_preview', 'reply_message_preview',
        'parent_sender', 'reply_sender', 'created_at'
    ]
    search_fields = [
        'parent_message__content', 'reply_message__content',
        'parent_message__sender__email', 'reply_message__sender__email', 'id'
    ]
    readonly_fields = ['id', 'created_at']
    raw_id_fields = ['parent_message', 'reply_message']
    date_hierarchy = 'created_at'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'parent_message', 'parent_message__sender',
            'reply_message', 'reply_message__sender'
        )
    
    def parent_message_preview(self, obj):
        content = obj.parent_message.content
        return content[:30] + "..." if len(content) > 30 else content
    parent_message_preview.short_description = 'Parent Message'
    
    def reply_message_preview(self, obj):
        content = obj.reply_message.content
        return content[:30] + "..." if len(content) > 30 else content
    reply_message_preview.short_description = 'Reply Message'
    
    def parent_sender(self, obj):
        return obj.parent_message.sender.email
    parent_sender.short_description = 'Parent Sender'
    parent_sender.admin_order_field = 'parent_message__sender__email'
    
    def reply_sender(self, obj):
        return obj.reply_message.sender.email
    reply_sender.short_description = 'Reply Sender'
    reply_sender.admin_order_field = 'reply_message__sender__email'


@admin.register(ChatSettings)
class ChatSettingsAdmin(admin.ModelAdmin):
    """Admin interface for ChatSettings"""
    list_display = [
        'id', 'user_email', 'email_notifications', 'push_notifications',
        'theme', 'show_typing_indicators', 'show_read_receipts'
    ]
    list_filter = [
        'email_notifications', 'push_notifications', 'desktop_notifications',
        'theme', 'show_typing_indicators', 'show_read_receipts',
        'auto_download_files', 'allow_direct_messages'
    ]
    search_fields = ['user__email', 'id']
    readonly_fields = ['id', 'created_at', 'updated_at']
    fieldsets = (
        ('User', {
            'fields': ('id', 'user')
        }),
        ('Notifications', {
            'fields': (
                'email_notifications', 'push_notifications',
                'desktop_notifications', 'sound_notifications'
            )
        }),
        ('Chat Preferences', {
            'fields': (
                'show_typing_indicators', 'show_read_receipts',
                'auto_download_files', 'theme'
            )
        }),
        ('Privacy', {
            'fields': ('allow_direct_messages',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    raw_id_fields = ['user']
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user')
    
    def user_email(self, obj):
        return obj.user.email
    user_email.short_description = 'User'
    user_email.admin_order_field = 'user__email'


# Custom admin actions
def mark_messages_as_read(modeladmin, request, queryset):
    """Mark selected messages as read"""
    updated = queryset.update(is_read=True)
    modeladmin.message_user(request, f"{updated} messages marked as read.")
mark_messages_as_read.short_description = "Mark selected messages as read"

def mark_messages_as_unread(modeladmin, request, queryset):
    """Mark selected messages as unread"""
    updated = queryset.update(is_read=False)
    modeladmin.message_user(request, f"{updated} messages marked as unread.")
mark_messages_as_unread.short_description = "Mark selected messages as unread"

def soft_delete_messages(modeladmin, request, queryset):
    """Soft delete selected messages"""
    updated = queryset.update(is_deleted=True)
    modeladmin.message_user(request, f"{updated} messages soft deleted.")
soft_delete_messages.short_description = "Soft delete selected messages"

def restore_messages(modeladmin, request, queryset):
    """Restore soft deleted messages"""
    updated = queryset.update(is_deleted=False)
    modeladmin.message_user(request, f"{updated} messages restored.")
restore_messages.short_description = "Restore selected messages"

# Add actions to ChatMessageAdmin
ChatMessageAdmin.actions = [
    mark_messages_as_read, mark_messages_as_unread,
    soft_delete_messages, restore_messages
]