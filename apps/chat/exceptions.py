from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status
import logging

logger = logging.getLogger(__name__)


def custom_exception_handler(exc, context):
    """Custom exception handler for chat-related errors"""
    
    # Call REST framework's default exception handler first
    response = exception_handler(exc, context)
    
    if response is not None:
        custom_response_data = {
            'error': True,
            'message': 'An error occurred',
            'details': response.data
        }
        
        # Log the error
        logger.error(f"Chat API Error: {exc} - Context: {context}")
        
        response.data = custom_response_data
    
    return response


class ChatRoomNotFoundError(Exception):
    """Exception raised when chat room is not found"""
    pass


class MessageNotFoundError(Exception):
    """Exception raised when message is not found"""
    pass


class InsufficientPermissionsError(Exception):
    """Exception raised when user doesn't have required permissions"""
    pass