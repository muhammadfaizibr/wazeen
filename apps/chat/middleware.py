
# apps/chat/middleware.py
from channels.middleware import BaseMiddleware
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import UntypedToken
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from django.conf import settings
import jwt

User = get_user_model()


class JWTAuthMiddleware(BaseMiddleware):
    """Custom JWT authentication middleware for WebSocket connections"""
    
    def __init__(self, inner):
        super().__init__(inner)
    
    async def __call__(self, scope, receive, send):
        # Get the token from query string or headers
        token = None
        
        # Try to get token from query string
        query_string = scope.get('query_string', b'').decode('utf-8')
        if query_string:
            query_params = dict(param.split('=') for param in query_string.split('&') if '=' in param)
            token = query_params.get('token')
        
        # Try to get token from headers if not in query string
        if not token:
            headers = dict(scope['headers'])
            authorization = headers.get(b'authorization')
            if authorization:
                try:
                    auth_header = authorization.decode('utf-8')
                    if auth_header.startswith('Bearer '):
                        token = auth_header.split(' ')[1]
                except UnicodeDecodeError:
                    pass
        
        # Authenticate user with token
        scope['user'] = await self.get_user(token)
        return await super().__call__(scope, receive, send)
    
    @database_sync_to_async
    def get_user(self, token):
        """Get user from JWT token"""
        if not token:
            return AnonymousUser()
        
        try:
            # Validate token
            UntypedToken(token)
            
            # Decode token to get user info
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=['HS256'])
            user_id = payload.get('user_id')
            
            if user_id:
                user = User.objects.get(id=user_id)
                return user
                
        except (InvalidToken, TokenError, jwt.InvalidTokenError, User.DoesNotExist):
            pass
        
        return AnonymousUser()


def JWTAuthMiddlewareStack(inner):
    """Apply JWT authentication middleware to WebSocket connections"""
    return JWTAuthMiddleware(inner)


# Update core/routing.py to use JWT middleware
# application = ProtocolTypeRouter({
#     "http": get_asgi_application(),
#     "websocket": AllowedHostsOriginValidator(
#         JWTAuthMiddlewareStack(
#             URLRouter(websocket_urlpatterns)
#         )
#     ),
# })