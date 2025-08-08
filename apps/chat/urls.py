# apps/chat/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

app_name = 'chat'

# Router for ViewSets
router = DefaultRouter()
router.register(
    r'rooms/(?P<room_id>[0-9a-f-]+)/messages',
    views.ChatMessageViewSet,
    basename='messages'
)

urlpatterns = [
    # Chat room URLs
    path('rooms/', views.ChatRoomListCreateView.as_view(), name='room-list'),
    path('rooms/<uuid:pk>/', views.ChatRoomDetailView.as_view(), name='room-detail'),
    
    # Message ViewSet URLs (includes all CRUD + custom actions)
    path('', include(router.urls)),
    
    # Typing indicator
    path('rooms/<uuid:room_id>/typing/', views.set_typing_indicator, name='typing-indicator'),
    
    # Chat settings
    path('settings/', views.ChatSettingsView.as_view(), name='chat-settings'),
    
    # Chat statistics
    path('rooms/<uuid:room_id>/stats/', views.chat_stats, name='chat-stats'),
    
    # Search messages
    path('rooms/<uuid:room_id>/search/', views.search_messages, name='search-messages'),
    
    # Export chat
    path('rooms/<uuid:room_id>/export/', views.export_chat, name='export-chat'),
    
    # Clear chat history (admin only)
    path('rooms/<uuid:room_id>/clear/', views.clear_chat_history, name='clear-chat'),
    
    # Message threads
    path('rooms/<uuid:room_id>/messages/<uuid:message_id>/thread/', 
         views.MessageThreadView.as_view(), name='message-thread'),
    
    # Admin cleanup tasks
    path('admin/cleanup-typing/', views.cleanup_typing_indicators, name='cleanup-typing'),
]

"""
Available endpoints:

Chat Rooms:
- GET /api/chat/rooms/ - List chat rooms
- GET /api/chat/rooms/{room_id}/ - Get room details

Messages:
- GET /api/chat/rooms/{room_id}/messages/ - List messages (paginated)
- POST /api/chat/rooms/{room_id}/messages/ - Create new message
- GET /api/chat/rooms/{room_id}/messages/{message_id}/ - Get message details
- PATCH /api/chat/rooms/{room_id}/messages/{message_id}/ - Update message
- DELETE /api/chat/rooms/{room_id}/messages/{message_id}/ - Delete message

Message Actions:
- POST /api/chat/rooms/{room_id}/messages/{message_id}/react/ - Add reaction
- DELETE /api/chat/rooms/{room_id}/messages/{message_id}/react/{emoji}/ - Remove reaction
- POST /api/chat/rooms/{room_id}/messages/mark_as_read/ - Mark messages as read

Additional Features:
- POST /api/chat/rooms/{room_id}/typing/ - Set typing indicator
- GET /api/chat/settings/ - Get chat settings
- PATCH /api/chat/settings/ - Update chat settings
- GET /api/chat/rooms/{room_id}/stats/ - Get chat statistics
- GET /api/chat/rooms/{room_id}/search/?q=query - Search messages
- POST /api/chat/rooms/{room_id}/export/ - Export chat
- DELETE /api/chat/rooms/{room_id}/clear/ - Clear chat (admin)
- GET /api/chat/rooms/{room_id}/messages/{message_id}/thread/ - Get thread replies

WebSocket Endpoints:
- ws://domain/ws/chat/{room_id}/ - Chat room WebSocket
- ws://domain/ws/notifications/ - System notifications WebSocket
"""


# Main project urls.py integration