# apps/chat/routing.py
from django.urls import re_path, path
from . import consumers

websocket_urlpatterns = [
    # Chat room WebSocket
    re_path(r'ws/chat/(?P<room_id>[0-9a-f-]+)/$', consumers.ChatConsumer.as_asgi()),
    
    # System notifications WebSocket
    path('ws/notifications/', consumers.NotificationConsumer.as_asgi()),
]
