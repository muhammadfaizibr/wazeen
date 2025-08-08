from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import Http404
from django.db import IntegrityError
from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from rest_framework.exceptions import (
    ValidationError,
    AuthenticationFailed,
    NotAuthenticated,
    PermissionDenied,
    NotFound,
    MethodNotAllowed,
    ThrottleException
)
import logging

logger = logging.getLogger(__name__)


class BaseAPIException(Exception):
    """Base exception for API errors"""
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    default_message = 'An error occurred'
    error_code = 'INTERNAL_ERROR'
    
    def __init__(self, message=None, status_code=None, error_code=None, details=None):
        self.message = message or self.default_message
        self.status_code = status_code or self.status_code
        self.error_code = error_code or self.error_code
        self.details = details
        super().__init__(self.message)


class BusinessLogicError(BaseAPIException):
    """Business logic validation error"""
    status_code = status.HTTP_400_BAD_REQUEST
    default_message = 'Business logic validation failed'
    error_code = 'BUSINESS_LOGIC_ERROR'


class ResourceNotFoundError(BaseAPIException):
    """Resource not found error"""
    status_code = status.HTTP_404_NOT_FOUND
    default_message = 'Resource not found'
    error_code = 'RESOURCE_NOT_FOUND'


class DuplicateResourceError(BaseAPIException):
    """Duplicate resource error"""
    status_code = status.HTTP_409_CONFLICT
    default_message = 'Resource already exists'
    error_code = 'DUPLICATE_RESOURCE'


class FileProcessingError(BaseAPIException):
    """File processing error"""
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_message = 'File processing failed'
    error_code = 'FILE_PROCESSING_ERROR'


class ServiceUnavailableError(BaseAPIException):
    """Service unavailable error"""
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_message = 'Service temporarily unavailable'
    error_code = 'SERVICE_UNAVAILABLE'


class RateLimitExceededError(BaseAPIException):
    """Rate limit exceeded error"""
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    default_message = 'Rate limit exceeded'
    error_code = 'RATE_LIMIT_EXCEEDED'


class PaymentRequiredError(BaseAPIException):
    """Payment required error"""
    status_code = status.HTTP_402_PAYMENT_REQUIRED
    default_message = 'Payment required'
    error_code = 'PAYMENT_REQUIRED'


class InsufficientPermissionsError(BaseAPIException):
    """Insufficient permissions error"""
    status_code = status.HTTP_403_FORBIDDEN
    default_message = 'Insufficient permissions'
    error_code = 'INSUFFICIENT_PERMISSIONS'


class AccountSuspendedError(BaseAPIException):
    """Account suspended error"""
    status_code = status.HTTP_403_FORBIDDEN
    default_message = 'Account has been suspended'
    error_code = 'ACCOUNT_SUSPENDED'


class EmailNotVerifiedError(BaseAPIException):
    """Email not verified error"""
    status_code = status.HTTP_403_FORBIDDEN
    default_message = 'Email address not verified'
    error_code = 'EMAIL_NOT_VERIFIED'


class InvalidTokenError(BaseAPIException):
    """Invalid token error"""
    status_code = status.HTTP_401_UNAUTHORIZED
    default_message = 'Invalid or expired token'
    error_code = 'INVALID_TOKEN'


class DatabaseError(BaseAPIException):
    """Database operation error"""
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    default_message = 'Database operation failed'
    error_code = 'DATABASE_ERROR'


class ExternalAPIError(BaseAPIException):
    """External API error"""
    status_code = status.HTTP_502_BAD_GATEWAY
    default_message = 'External service error'
    error_code = 'EXTERNAL_API_ERROR'


class ConfigurationError(BaseAPIException):
    """Configuration error"""
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    default_message = 'System configuration error'
    error_code = 'CONFIGURATION_ERROR'


def custom_exception_handler(exc, context):
    """Custom exception handler for DRF"""
    
    # Call REST framework's default exception handler first
    response = exception_handler(exc, context)
    
    # Get the view and request from context
    view = context.get('view', None)
    request = context.get('request', None)
    
    # Log the exception
    if hasattr(view, 'get_view_name'):
        view_name = view.get_view_name()
    else:
        view_name = view.__class__.__name__ if view else 'Unknown'
    
    logger.error(
        f"Exception in {view_name}: {exc.__class__.__name__}: {str(exc)}",
        extra={
            'view': view_name,
            'user': getattr(request, 'user', None),
            'method': getattr(request, 'method', None),
            'path': getattr(request, 'path', None),
        },
        exc_info=True
    )
    
    # Handle custom API exceptions
    if isinstance(exc, BaseAPIException):
        custom_response_data = {
            'success': False,
            'error': {
                'code': exc.error_code,
                'message': exc.message,
                'details': exc.details
            }
        }
        return Response(custom_response_data, status=exc.status_code)
    
    # Handle Django validation errors
    if isinstance(exc, DjangoValidationError):
        if hasattr(exc, 'message_dict'):
            # Field-specific errors
            custom_response_data = {
                'success': False,
                'error': {
                    'code': 'VALIDATION_ERROR',
                    'message': 'Validation failed',
                    'details': exc.message_dict
                }
            }
        elif hasattr(exc, 'messages'):
            # Non-field errors
            custom_response_data = {
                'success': False,
                'error': {
                    'code': 'VALIDATION_ERROR',
                    'message': 'Validation failed',
                    'details': {'non_field_errors': exc.messages}
                }
            }
        else:
            # Single message
            custom_response_data = {
                'success': False,
                'error': {
                    'code': 'VALIDATION_ERROR',
                    'message': str(exc),
                    'details': None
                }
            }
        return Response(custom_response_data, status=status.HTTP_400_BAD_REQUEST)
    
    # Handle Django Http404
    if isinstance(exc, Http404):
        custom_response_data = {
            'success': False,
            'error': {
                'code': 'NOT_FOUND',
                'message': 'Resource not found',
                'details': None
            }
        }
        return Response(custom_response_data, status=status.HTTP_404_NOT_FOUND)
    
    # Handle Django IntegrityError
    if isinstance(exc, IntegrityError):
        custom_response_data = {
            'success': False,
            'error': {
                'code': 'INTEGRITY_ERROR',
                'message': 'Database integrity constraint violated',
                'details': str(exc) if hasattr(exc, 'args') and exc.args else None
            }
        }
        return Response(custom_response_data, status=status.HTTP_409_CONFLICT)
    
    # Handle Django PermissionDenied
    if isinstance(exc, DjangoPermissionDenied):
        custom_response_data = {
            'success': False,
            'error': {
                'code': 'PERMISSION_DENIED',
                'message': 'Permission denied',
                'details': str(exc) if str(exc) else None
            }
        }
        return Response(custom_response_data, status=status.HTTP_403_FORBIDDEN)
    
    # Handle DRF exceptions that weren't handled by default handler
    if isinstance(exc, ValidationError):
        custom_response_data = {
            'success': False,
            'error': {
                'code': 'VALIDATION_ERROR',
                'message': 'Validation failed',
                'details': exc.detail if hasattr(exc, 'detail') else str(exc)
            }
        }
        return Response(custom_response_data, status=status.HTTP_400_BAD_REQUEST)
    
    if isinstance(exc, AuthenticationFailed):
        custom_response_data = {
            'success': False,
            'error': {
                'code': 'AUTHENTICATION_FAILED',
                'message': 'Authentication failed',
                'details': str(exc)
            }
        }
        return Response(custom_response_data, status=status.HTTP_401_UNAUTHORIZED)
    
    if isinstance(exc, NotAuthenticated):
        custom_response_data = {
            'success': False,
            'error': {
                'code': 'NOT_AUTHENTICATED',
                'message': 'Authentication required',
                'details': str(exc)
            }
        }
        return Response(custom_response_data, status=status.HTTP_401_UNAUTHORIZED)
    
    if isinstance(exc, PermissionDenied):
        custom_response_data = {
            'success': False,
            'error': {
                'code': 'PERMISSION_DENIED',
                'message': 'Permission denied',
                'details': str(exc)
            }
        }
        return Response(custom_response_data, status=status.HTTP_403_FORBIDDEN)
    
    if isinstance(exc, NotFound):
        custom_response_data = {
            'success': False,
            'error': {
                'code': 'NOT_FOUND',
                'message': 'Resource not found',
                'details': str(exc)
            }
        }
        return Response(custom_response_data, status=status.HTTP_404_NOT_FOUND)
    
    if isinstance(exc, MethodNotAllowed):
        custom_response_data = {
            'success': False,
            'error': {
                'code': 'METHOD_NOT_ALLOWED',
                'message': 'Method not allowed',
                'details': {
                    'method': getattr(request, 'method', None),
                    'allowed_methods': getattr(exc, 'detail', {}).get('allowed_methods', [])
                }
            }
        }
        return Response(custom_response_data, status=status.HTTP_405_METHOD_NOT_ALLOWED)
    
    if isinstance(exc, ThrottleException):
        custom_response_data = {
            'success': False,
            'error': {
                'code': 'THROTTLE_EXCEEDED',
                'message': 'Rate limit exceeded',
                'details': {
                    'available_in': getattr(exc, 'wait', None)
                }
            }
        }
        return Response(custom_response_data, status=status.HTTP_429_TOO_MANY_REQUESTS)
    
    # If we have a response from the default handler but it's not in our custom format
    if response is not None:
        custom_response_data = {
            'success': False,
            'error': {
                'code': 'API_ERROR',
                'message': 'An error occurred',
                'details': response.data
            }
        }
        return Response(custom_response_data, status=response.status_code)
    
    # Handle unexpected exceptions
    custom_response_data = {
        'success': False,
        'error': {
            'code': 'INTERNAL_ERROR',
            'message': 'An unexpected error occurred',
            'details': None
        }
    }
    return Response(custom_response_data, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


def format_error_response(error_code, message, details=None, status_code=status.HTTP_400_BAD_REQUEST):
    """Helper function to format consistent error responses"""
    return Response({
        'success': False,
        'error': {
            'code': error_code,
            'message': message,
            'details': details
        }
    }, status=status_code)


def format_success_response(data=None, message=None, status_code=status.HTTP_200_OK):
    """Helper function to format consistent success responses"""
    response_data = {'success': True}
    
    if data is not None:
        response_data['data'] = data
    
    if message is not None:
        response_data['message'] = message
    
    return Response(response_data, status=status_code)