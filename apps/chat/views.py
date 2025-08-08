# apps/chat/views.py
from rest_framework import generics, status, permissions
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters
from django.shortcuts import get_object_or_404
from django.db.models import Q, Count, Avg
from django.utils import timezone
from datetime import timedelta
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
import json

from apps.service_requests.models import ServiceRequest
from utils.pagination import StandardResultsSetPagination, SmallResultsSetPagination
from utils.permissions import IsOwnerOrReadOnly
from .models import (
    ChatRoom, ChatMessage, MessageReaction, ChatParticipant,
    TypingIndicator, MessageThread, ChatSettings
)
from .serializers import (
    ChatRoomSerializer, ChatRoomListSerializer,
    ChatMessageSerializer, ChatMessageListSerializer,
    ChatMessageCreateSerializer, ChatMessageUpdateSerializer,
    MessageReactionSerializer, MessageReactionCreateSerializer,
    ChatParticipantSerializer, TypingIndicatorSerializer,
    ChatSettingsSerializer, BulkMarkAsReadSerializer,
    ChatStatsSerializer
)
from .filters import ChatMessageFilter
from .permissions import ChatPermission


class ChatRoomListCreateView(generics.ListCreateAPIView):
    """List chat rooms for the current user"""
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['request__title', 'request__description']
    ordering_fields = ['created_at', 'updated_at']
    ordering = ['-updated_at']
    
    def get_queryset(self):
        user = self.request.user
        queryset = ChatRoom.objects.select_related('request', 'request__client', 'request__accountant')
        
        if user.role == 'admin':
            return queryset.all()
        elif user.role == 'client':
            return queryset.filter(request__client=user)
        elif user.role == 'accountant':
            return queryset.filter(
                Q(request__accountant=user) | Q(request__accountant__isnull=True)
            )
        return ChatRoom.objects.none()
    
    def get_serializer_class(self):
        if self.request.method == 'GET':
            return ChatRoomListSerializer
        return ChatRoomSerializer
    
    def create(self, request, *args, **kwargs):
        # Chat rooms are auto-created with service requests
        return Response(
            {'error': 'Chat rooms are automatically created with service requests'},
            status=status.HTTP_400_BAD_REQUEST
        )


class ChatRoomDetailView(generics.RetrieveUpdateAPIView):
    """Retrieve and update chat room details"""
    serializer_class = ChatRoomSerializer
    permission_classes = [permissions.IsAuthenticated, ChatPermission]
    
    def get_queryset(self):
        user = self.request.user
        queryset = ChatRoom.objects.select_related('request', 'request__client', 'request__accountant')
        
        if user.role == 'admin':
            return queryset.all()
        elif user.role == 'client':
            return queryset.filter(request__client=user)
        elif user.role == 'accountant':
            return queryset.filter(
                Q(request__accountant=user) | Q(request__accountant__isnull=True)
            )
        return ChatRoom.objects.none()
    
    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        
        # Update participant's last seen
        participant, created = ChatParticipant.objects.get_or_create(
            room=instance,
            user=request.user,
            defaults={'is_active': True}
        )
        participant.last_seen = timezone.now()
        participant.save(update_fields=['last_seen'])
        
        serializer = self.get_serializer(instance)
        return Response(serializer.data)


class ChatMessageViewSet(ModelViewSet):
    """ViewSet for chat messages"""
    permission_classes = [permissions.IsAuthenticated, ChatPermission]
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = ChatMessageFilter
    search_fields = ['content']
    ordering_fields = ['created_at']
    ordering = ['-created_at']
    
    def get_queryset(self):
        room_id = self.kwargs.get('room_id')
        room = get_object_or_404(ChatRoom, id=room_id)
        
        # Check access permissions
        if not room.can_user_access(self.request.user):
            return ChatMessage.objects.none()
        
        return ChatMessage.objects.filter(
            room=room,
            is_deleted=False
        ).select_related('sender', 'file').prefetch_related('reactions', 'reactions__user')
    
    def get_serializer_class(self):
        if self.action == 'list':
            return ChatMessageListSerializer
        elif self.action == 'create':
            return ChatMessageCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return ChatMessageUpdateSerializer
        return ChatMessageSerializer
    
    def get_serializer_context(self):
        context = super().get_serializer_context()
        room_id = self.kwargs.get('room_id')
        if room_id:
            context['room'] = get_object_or_404(ChatRoom, id=room_id)
        return context
    
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        message = serializer.save()
        
        # Broadcast message to WebSocket consumers
        self.broadcast_message(message, 'message_created')
        
        # Update room's updated_at timestamp
        message.room.save(update_fields=['updated_at'])
        
        # Create participant record if not exists
        ChatParticipant.objects.get_or_create(
            room=message.room,
            user=request.user,
            defaults={'is_active': True}
        )
        
        response_serializer = ChatMessageSerializer(message, context=self.get_serializer_context())
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)
    
    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        message = serializer.save()
        
        # Broadcast message update
        self.broadcast_message(message, 'message_updated')
        
        response_serializer = ChatMessageSerializer(message, context=self.get_serializer_context())
        return Response(response_serializer.data)
    
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        
        if not instance.can_user_delete(request.user):
            return Response(
                {'error': 'You cannot delete this message'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Soft delete
        instance.is_deleted = True
        instance.save(update_fields=['is_deleted'])
        
        # Broadcast deletion
        self.broadcast_message(instance, 'message_deleted')
        
        return Response(status=status.HTTP_204_NO_CONTENT)
    
    def broadcast_message(self, message, action):
        """Broadcast message to WebSocket consumers"""
        channel_layer = get_channel_layer()
        room_group_name = f'chat_{message.room.id}'
        
        serializer = ChatMessageSerializer(message, context=self.get_serializer_context())
        
        async_to_sync(channel_layer.group_send)(
            room_group_name,
            {
                'type': 'chat_message',
                'action': action,
                'message': serializer.data
            }
        )
    
    @action(detail=True, methods=['post'])
    def react(self, request, room_id=None, pk=None):
        """Add reaction to a message"""
        message = self.get_object()
        serializer = MessageReactionCreateSerializer(
            data=request.data,
            context={'request': request, 'message': message}
        )
        serializer.is_valid(raise_exception=True)
        reaction = serializer.save()
        
        # Broadcast reaction
        channel_layer = get_channel_layer()
        room_group_name = f'chat_{message.room.id}'
        
        async_to_sync(channel_layer.group_send)(
            room_group_name,
            {
                'type': 'message_reaction',
                'action': 'reaction_added',
                'message_id': str(message.id),
                'reaction': MessageReactionSerializer(reaction).data
            }
        )
        
        return Response(MessageReactionSerializer(reaction).data, status=status.HTTP_201_CREATED)
    
    @action(detail=True, methods=['delete'], url_path='react/(?P<emoji>[^/.]+)')
    def remove_reaction(self, request, room_id=None, pk=None, emoji=None):
        """Remove reaction from a message"""
        message = self.get_object()
        
        try:
            reaction = MessageReaction.objects.get(
                message=message,
                user=request.user,
                emoji=emoji
            )
            reaction.delete()
            
            # Broadcast reaction removal
            channel_layer = get_channel_layer()
            room_group_name = f'chat_{message.room.id}'
            
            async_to_sync(channel_layer.group_send)(
                room_group_name,
                {
                    'type': 'message_reaction',
                    'action': 'reaction_removed',
                    'message_id': str(message.id),
                    'emoji': emoji,
                    'user_id': str(request.user.id)
                }
            )
            
            return Response(status=status.HTTP_204_NO_CONTENT)
        except MessageReaction.DoesNotExist:
            return Response(
                {'error': 'Reaction not found'},
                status=status.HTTP_404_NOT_FOUND
            )
    
    @action(detail=False, methods=['post'])
    def mark_as_read(self, request, room_id=None):
        """Mark messages as read up to a specific message"""
        serializer = BulkMarkAsReadSerializer(
            data=request.data,
            context={'room': get_object_or_404(ChatRoom, id=room_id)}
        )
        serializer.is_valid(raise_exception=True)
        
        message = serializer.validated_data['message_id']
        room = get_object_or_404(ChatRoom, id=room_id)
        
        # Get or create participant
        participant, created = ChatParticipant.objects.get_or_create(
            room=room,
            user=request.user,
            defaults={'is_active': True}
        )
        
        # Mark messages as read
        participant.mark_as_read(message)
        
        # Broadcast read status
        channel_layer = get_channel_layer()
        room_group_name = f'chat_{room.id}'
        
        async_to_sync(channel_layer.group_send)(
            room_group_name,
            {
                'type': 'messages_read',
                'user_id': str(request.user.id),
                'message_id': str(message.id),
                'read_at': timezone.now().isoformat()
            }
        )
        
        return Response({'detail': 'Messages marked as read'})


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def set_typing_indicator(request, room_id):
    """Set typing indicator for a user in a chat room"""
    room = get_object_or_404(ChatRoom, id=room_id)
    
    if not room.can_user_access(request.user):
        return Response(
            {'error': 'You do not have access to this chat room'},
            status=status.HTTP_403_FORBIDDEN
        )
    
    is_typing = request.data.get('is_typing', False)
    
    if is_typing:
        # Update or create typing indicator
        indicator, created = TypingIndicator.objects.update_or_create(
            room=room,
            user=request.user,
            defaults={'is_typing': True, 'updated_at': timezone.now()}
        )
    else:
        # Remove typing indicator
        TypingIndicator.objects.filter(room=room, user=request.user).delete()
    
    # Broadcast typing status
    channel_layer = get_channel_layer()
    room_group_name = f'chat_{room.id}'
    
    async_to_sync(channel_layer.group_send)(
        room_group_name,
        {
            'type': 'typing_indicator',
            'user_id': str(request.user.id),
            'user_name': request.user.full_name,
            'is_typing': is_typing
        }
    )
    
    return Response({'detail': 'Typing indicator updated'})


class ChatSettingsView(generics.RetrieveUpdateAPIView):
    """User's chat settings"""
    serializer_class = ChatSettingsSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_object(self):
        settings_obj, created = ChatSettings.objects.get_or_create(
            user=self.request.user
        )
        return settings_obj


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def chat_stats(request, room_id):
    """Get chat statistics for a room"""
    room = get_object_or_404(ChatRoom, id=room_id)
    
    if not room.can_user_access(request.user):
        return Response(
            {'error': 'You do not have access to this chat room'},
            status=status.HTTP_403_FORBIDDEN
        )
    
    # Calculate statistics
    total_messages = room.messages.filter(is_deleted=False).count()
    total_files = room.messages.filter(
        is_deleted=False,
        message_type__in=['file', 'image', 'document']
    ).count()
    
    active_participants = ChatParticipant.objects.filter(
        room=room,
        is_active=True
    ).count()
    
    # Messages today
    today = timezone.now().date()
    messages_today = room.messages.filter(
        is_deleted=False,
        created_at__date=today
    ).count()
    
    # Calculate average response time (simplified)
    messages_with_responses = room.messages.filter(
        is_deleted=False,
        thread__isnull=False
    ).annotate(
        response_time=Avg('thread__reply_message__created_at') - Avg('created_at')
    ).aggregate(avg_response_time=Avg('response_time'))
    
    avg_response_time = 0
    if messages_with_responses['avg_response_time']:
        avg_response_time = messages_with_responses['avg_response_time'].total_seconds() / 60
    
    stats = {
        'total_messages': total_messages,
        'total_files_shared': total_files,
        'active_participants': active_participants,
        'messages_today': messages_today,
        'average_response_time': round(avg_response_time, 2)
    }
    
    serializer = ChatStatsSerializer(data=stats)
    serializer.is_valid()
    
    return Response(serializer.data)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def search_messages(request, room_id):
    """Search messages in a chat room"""
    room = get_object_or_404(ChatRoom, id=room_id)
    
    if not room.can_user_access(request.user):
        return Response(
            {'error': 'You do not have access to this chat room'},
            status=status.HTTP_403_FORBIDDEN
        )
    
    query = request.query_params.get('q', '').strip()
    if not query:
        return Response({'results': []})
    
    # Search messages
    messages = room.messages.filter(
        is_deleted=False,
        content__icontains=query
    ).select_related('sender', 'file').order_by('-created_at')[:50]
    
    serializer = ChatMessageListSerializer(
        messages,
        many=True,
        context={'request': request}
    )
    
    return Response({'results': serializer.data})


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def export_chat(request, room_id):
    """Export chat messages to a file"""
    room = get_object_or_404(ChatRoom, id=room_id)
    
    if not room.can_user_access(request.user):
        return Response(
            {'error': 'You do not have access to this chat room'},
            status=status.HTTP_403_FORBIDDEN
        )
    
    # This would typically be handled by a background task
    # For now, return success message
    return Response({
        'detail': 'Chat export has been queued. You will receive an email when ready.'
    })


@api_view(['DELETE'])
@permission_classes([permissions.IsAuthenticated])
def clear_chat_history(request, room_id):
    """Clear chat history (admin only)"""
    if request.user.role != 'admin':
        return Response(
            {'error': 'Only administrators can clear chat history'},
            status=status.HTTP_403_FORBIDDEN
        )
    
    room = get_object_or_404(ChatRoom, id=room_id)
    
    # Soft delete all messages
    room.messages.update(is_deleted=True)
    
    # Broadcast clear event
    channel_layer = get_channel_layer()
    room_group_name = f'chat_{room.id}'
    
    async_to_sync(channel_layer.group_send)(
        room_group_name,
        {
            'type': 'chat_cleared',
            'cleared_by': request.user.full_name,
            'cleared_at': timezone.now().isoformat()
        }
    )
    
    return Response({'detail': 'Chat history cleared'})


class MessageThreadView(generics.ListAPIView):
    """Get message thread (replies to a message)"""
    serializer_class = ChatMessageSerializer
    permission_classes = [permissions.IsAuthenticated, ChatPermission]
    pagination_class = SmallResultsSetPagination
    
    def get_queryset(self):
        room_id = self.kwargs.get('room_id')
        message_id = self.kwargs.get('message_id')
        
        room = get_object_or_404(ChatRoom, id=room_id)
        if not room.can_user_access(self.request.user):
            return ChatMessage.objects.none()
        
        parent_message = get_object_or_404(ChatMessage, id=message_id, room=room)
        
        # Get all replies to this message
        reply_ids = MessageThread.objects.filter(
            parent_message=parent_message
        ).values_list('reply_message_id', flat=True)
        
        return ChatMessage.objects.filter(
            id__in=reply_ids,
            is_deleted=False
        ).select_related('sender', 'file').prefetch_related('reactions')


# Cleanup task view (for admin)
@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def cleanup_typing_indicators(request):
    """Clean up old typing indicators (admin only)"""
    if request.user.role != 'admin':
        return Response(
            {'error': 'Only administrators can perform cleanup tasks'},
            status=status.HTTP_403_FORBIDDEN
        )
    
    # Clean up typing indicators older than 5 minutes
    TypingIndicator.cleanup_old_indicators(minutes=5)
    
    return Response({'detail': 'Typing indicators cleaned up'})