# utils/middleware.py
import time
import json
import logging
import uuid
from datetime import datetime
from django.utils.deprecation import MiddlewareMixin
from django.http import JsonResponse
from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.core.cache import cache
from django.db import connection
from django.urls import resolve, Resolver404


logger = logging.getLogger(__name__)
audit_logger = logging.getLogger('audit')


class PerformanceMiddleware(MiddlewareMixin):
    """
    Middleware to monitor application performance and log slow requests
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
        self.slow_request_threshold = getattr(settings, 'SLOW_REQUEST_THRESHOLD', 5.0)  # 5 seconds
        self.monitor_db_queries = getattr(settings, 'MONITOR_DB_QUERIES', True)
        self.cache_stats = getattr(settings, 'CACHE_PERFORMANCE_STATS', True)
        super().__init__(get_response)
    
    def process_request(self, request):
        """Start timing the request"""
        request.start_time = time.time()
        request.request_id = str(uuid.uuid4())[:8]
        
        # Store initial DB query count
        if self.monitor_db_queries:
            request.db_queries_start = len(connection.queries)
        
        return None
    
    def process_response(self, request, response):
        """Calculate and log performance metrics"""
        if not hasattr(request, 'start_time'):
            return response
        
        # Calculate total time
        total_time = time.time() - request.start_time
        
        # Get DB query count
        db_queries = 0
        db_time = 0
        if self.monitor_db_queries and hasattr(request, 'db_queries_start'):
            db_queries = len(connection.queries) - request.db_queries_start
            db_time = sum(float(query.get('time', 0)) for query in connection.queries[request.db_queries_start:])
        
        # Add performance headers
        response['X-Response-Time'] = f"{total_time:.3f}s"
        response['X-DB-Queries'] = str(db_queries)
        response['X-Request-ID'] = getattr(request, 'request_id', 'unknown')
        
        # Log performance data
        performance_data = {
            'request_id': getattr(request, 'request_id', 'unknown'),
            'method': request.method,
            'path': request.path,
            'user': str(request.user) if hasattr(request, 'user') and request.user.is_authenticated else 'Anonymous',
            'total_time': round(total_time, 3),
            'db_queries': db_queries,
            'db_time': round(db_time, 3),
            'status_code': response.status_code,
            'response_size': len(response.content) if hasattr(response, 'content') else 0
        }
        
        # Log slow requests
        if total_time > self.slow_request_threshold:
            logger.warning(f"Slow request detected: {json.dumps(performance_data)}")
        else:
            logger.info(f"Request performance: {json.dumps(performance_data)}")
        
        # Cache performance stats for monitoring dashboard
        if self.cache_stats:
            self._cache_performance_stats(performance_data)
        
        return response
    
    def _cache_performance_stats(self, data):
        """Cache performance statistics for monitoring"""
        try:
            # Store hourly performance stats
            current_hour = datetime.now().strftime('%Y-%m-%d-%H')
            cache_key = f"performance_stats_{current_hour}"
            
            stats = cache.get(cache_key, {
                'total_requests': 0,
                'total_time': 0,
                'total_db_queries': 0,
                'slow_requests': 0,
                'avg_response_time': 0
            })
            
            stats['total_requests'] += 1
            stats['total_time'] += data['total_time']
            stats['total_db_queries'] += data['db_queries']
            
            if data['total_time'] > self.slow_request_threshold:
                stats['slow_requests'] += 1
            
            stats['avg_response_time'] = stats['total_time'] / stats['total_requests']
            
            # Cache for 2 hours
            cache.set(cache_key, stats, 7200)
            
        except Exception as e:
            logger.error(f"Error caching performance stats: {e}")


class AuditMiddleware(MiddlewareMixin):
    """
    Middleware to log all requests for audit purposes
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
        self.audit_enabled = getattr(settings, 'AUDIT_LOGGING_ENABLED', True)
        self.log_body = getattr(settings, 'AUDIT_LOG_REQUEST_BODY', False)
        self.sensitive_fields = getattr(settings, 'SENSITIVE_FIELDS', [
            'password', 'token', 'secret', 'api_key', 'credit_card'
        ])
        self.excluded_paths = getattr(settings, 'AUDIT_EXCLUDED_PATHS', [
            '/admin/jsi18n/',
            '/static/',
            '/media/',
            '/health/',
            '/metrics/'
        ])
        super().__init__(get_response)
    
    def process_request(self, request):
        """Log request details"""
        if not self.audit_enabled:
            return None
        
        # Skip excluded paths
        if any(request.path.startswith(path) for path in self.excluded_paths):
            return None
        
        # Get user info
        user_info = self._get_user_info(request)
        
        # Get client IP
        client_ip = self._get_client_ip(request)
        
        # Prepare request data
        request_data = {
            'timestamp': datetime.now().isoformat(),
            'request_id': getattr(request, 'request_id', str(uuid.uuid4())[:8]),
            'method': request.method,
            'path': request.path,
            'query_params': dict(request.GET),
            'user': user_info,
            'ip_address': client_ip,
            'user_agent': request.META.get('HTTP_USER_AGENT', ''),
            'referer': request.META.get('HTTP_REFERER', ''),
        }
        
        # Add request body for non-GET requests (if enabled)
        if self.log_body and request.method != 'GET':
            try:
                body = self._get_request_body(request)
                if body:
                    request_data['body'] = self._sanitize_data(body)
            except Exception as e:
                request_data['body_error'] = str(e)
        
        # Try to resolve URL name
        try:
            resolved = resolve(request.path)
            request_data['view_name'] = f"{resolved.view_name}"
            request_data['url_name'] = resolved.url_name
        except Resolver404:
            pass
        
        # Store for response processing
        request._audit_data = request_data
        
        return None
    
    def process_response(self, request, response):
        """Log response details"""
        if not self.audit_enabled or not hasattr(request, '_audit_data'):
            return response
        
        audit_data = request._audit_data
        
        # Add response information
        audit_data.update({
            'response_status': response.status_code,
            'response_size': len(response.content) if hasattr(response, 'content') else 0,
            'processing_time': getattr(request, 'processing_time', 0),
        })
        
        # Log successful requests as INFO, errors as ERROR
        if 200 <= response.status_code < 400:
            audit_logger.info(json.dumps(audit_data))
        elif 400 <= response.status_code < 500:
            audit_logger.warning(json.dumps(audit_data))
        else:
            audit_logger.error(json.dumps(audit_data))
        
        return response
    
    def process_exception(self, request, exception):
        """Log exceptions"""
        if not self.audit_enabled or not hasattr(request, '_audit_data'):
            return None
        
        audit_data = request._audit_data
        audit_data.update({
            'exception': str(exception),
            'exception_type': type(exception).__name__,
        })
        
        audit_logger.error(json.dumps(audit_data))
        return None
    
    def _get_user_info(self, request):
        """Extract user information"""
        if not hasattr(request, 'user') or isinstance(request.user, AnonymousUser):
            return {'id': None, 'email': 'anonymous', 'role': 'anonymous'}
        
        user = request.user
        return {
            'id': str(user.id),
            'email': user.email,
            'role': getattr(user, 'role', 'unknown'),
            'is_staff': getattr(user, 'is_staff', False),
            'is_superuser': getattr(user, 'is_superuser', False)
        }
    
    def _get_client_ip(self, request):
        """Get client IP address"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR', '')
        return ip
    
    def _get_request_body(self, request):
        """Safely get request body"""
        if hasattr(request, 'body'):
            try:
                body = request.body.decode('utf-8')
                if body:
                    return json.loads(body)
            except (UnicodeDecodeError, json.JSONDecodeError):
                return None
        return None
    
    def _sanitize_data(self, data):
        """Remove sensitive data from logs"""
        if isinstance(data, dict):
            sanitized = {}
            for key, value in data.items():
                if any(sensitive in key.lower() for sensitive in self.sensitive_fields):
                    sanitized[key] = '***REDACTED***'
                elif isinstance(value, (dict, list)):
                    sanitized[key] = self._sanitize_data(value)
                else:
                    sanitized[key] = value
            return sanitized
        elif isinstance(data, list):
            return [self._sanitize_data(item) for item in data]
        return data


class SecurityMiddleware(MiddlewareMixin):
    """
    Security middleware for additional protection
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
        self.rate_limit_enabled = getattr(settings, 'RATE_LIMITING_ENABLED', True)
        self.blocked_ips = getattr(settings, 'BLOCKED_IPS', set())
        self.suspicious_patterns = getattr(settings, 'SUSPICIOUS_PATTERNS', [
            'wp-admin', 'phpmyadmin', '.env', 'config.php'
        ])
        super().__init__(get_response)
    
    def process_request(self, request):
        """Security checks before processing request"""
        client_ip = self._get_client_ip(request)
        
        # Check blocked IPs
        if client_ip in self.blocked_ips:
            logger.warning(f"Blocked IP attempted access: {client_ip}")
            return JsonResponse({'error': 'Access denied'}, status=403)
        
        # Check for suspicious patterns
        if any(pattern in request.path.lower() for pattern in self.suspicious_patterns):
            logger.warning(f"Suspicious path accessed: {request.path} from {client_ip}")
            # Could block immediately or just log
        
        # Basic rate limiting (simple implementation)
        if self.rate_limit_enabled:
            if self._is_rate_limited(client_ip):
                logger.warning(f"Rate limit exceeded for IP: {client_ip}")
                return JsonResponse({'error': 'Rate limit exceeded'}, status=429)
        
        return None
    
    def _get_client_ip(self, request):
        """Get client IP address"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR', '')
        return ip
    
    def _is_rate_limited(self, ip):
        """Simple rate limiting check using cache"""
        cache_key = f"rate_limit_{ip}"
        current_requests = cache.get(cache_key, 0)
        
        if current_requests >= 1000:  # 1000 requests per hour
            return True
        
        cache.set(cache_key, current_requests + 1, 3600)  # 1 hour
        return False


class RequestLoggingMiddleware(MiddlewareMixin):
    """
    Detailed request logging middleware for debugging
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
        self.debug_logging = getattr(settings, 'DEBUG_REQUEST_LOGGING', settings.DEBUG)
        super().__init__(get_response)
    
    def process_request(self, request):
        """Log detailed request information in DEBUG mode"""
        if not self.debug_logging:
            return None
        
        logger.debug(f"""
=== REQUEST DEBUG INFO ===
Method: {request.method}
Path: {request.path}
Query Params: {dict(request.GET)}
Headers: {dict(request.META)}
User: {getattr(request, 'user', 'Not set')}
Session: {dict(request.session) if hasattr(request, 'session') else 'No session'}
=========================""")
        
        return None


# utils/__init__.py
"""
Utils package for common utilities and middleware
"""

# utils/pagination.py
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from collections import OrderedDict


class CustomPagination(PageNumberPagination):
    """
    Custom pagination class with additional metadata
    """
    page_size = 25
    page_size_query_param = 'page_size'
    max_page_size = 100
    
    def get_paginated_response(self, data):
        return Response(OrderedDict([
            ('count', self.page.paginator.count),
            ('total_pages', self.page.paginator.num_pages),
            ('current_page', self.page.number),
            ('page_size', self.page.paginator.per_page),
            ('next', self.get_next_link()),
            ('previous', self.get_previous_link()),
            ('results', data)
        ]))


# utils/permissions.py
from rest_framework import permissions


class IsOwnerOrReadOnly(permissions.BasePermission):
    """
    Object-level permission to only allow owners of an object to edit it.
    Assumes the model instance has an `owner` attribute.
    """
    
    def has_object_permission(self, request, view, obj):
        # Read permissions are allowed to any request,
        # so we'll always allow GET, HEAD or OPTIONS requests.
        if request.method in permissions.SAFE_METHODS:
            return True
        
        # Instance must have an attribute named `owner`.
        return obj.owner == request.user


class IsAdminOrReadOnly(permissions.BasePermission):
    """
    Permission that only allows admins to modify objects
    """
    
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return request.user.is_authenticated
        
        return request.user.is_authenticated and getattr(request.user, 'role', None) == 'admin'


class IsAccountantOrAdmin(permissions.BasePermission):
    """
    Permission for accountants and admins
    """
    
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated and 
            getattr(request.user, 'role', None) in ['accountant', 'admin']
        )


# utils/exceptions.py
from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status
from django.core.exceptions import ValidationError
from django.db import IntegrityError
import logging


logger = logging.getLogger(__name__)


def custom_exception_handler(exc, context):
    """
    Custom exception handler for consistent error responses
    """
    # Call REST framework's default exception handler first
    response = exception_handler(exc, context)
    
    if response is not None:
        # Customize the error response format
        custom_response_data = {
            'error': {
                'status_code': response.status_code,
                'message': 'An error occurred',
                'details': response.data,
                'timestamp': context['request'].META.get('HTTP_X_REQUESTED_AT')
            }
        }
        
        # Log the error
        logger.error(f"API Error: {response.status_code} - {response.data}")
        
        response.data = custom_response_data
    
    # Handle Django ValidationError
    elif isinstance(exc, ValidationError):
        logger.error(f"Validation Error: {exc}")
        response = Response(
            {
                'error': {
                    'status_code': status.HTTP_400_BAD_REQUEST,
                    'message': 'Validation error',
                    'details': exc.message_dict if hasattr(exc, 'message_dict') else str(exc)
                }
            },
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Handle Database IntegrityError
    elif isinstance(exc, IntegrityError):
        logger.error(f"Database Integrity Error: {exc}")
        response = Response(
            {
                'error': {
                    'status_code': status.HTTP_400_BAD_REQUEST,
                    'message': 'Database constraint violation',
                    'details': 'The operation violates a database constraint'
                }
            },
            status=status.HTTP_400_BAD_REQUEST
        )
    
    return response


# utils/validators.py
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
import re


def validate_phone_number(value):
    """Validate phone number format"""
    phone_regex = re.compile(r'^\+?1?\d{9,15}$')
    if not phone_regex.match(value):
        raise ValidationError('Invalid phone number format')


def validate_file_size(value):
    """Validate file size (max 50MB)"""
    limit = 50 * 1024 * 1024  # 50MB
    if value.size > limit:
        raise ValidationError(f'File too large. Size should not exceed 50MB.')


password_validator = RegexValidator(
    regex=r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]{8,}$',
    message='Password must contain at least 8 characters with uppercase, lowercase, digit and special character'
)


# utils/helpers.py
import hashlib
import secrets
import string
from datetime import datetime, timedelta
from typing import Any, Dict, Optional
from django.core.mail import send_mail
from django.conf import settings
from django.template.loader import render_to_string
from django.utils.html import strip_tags


def generate_random_string(length: int = 32) -> str:
    """Generate a random string of specified length"""
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def hash_password(password: str) -> str:
    """Hash password using SHA-256"""
    return hashlib.sha256(password.encode()).hexdigest()


def send_notification_email(
    to_email: str, 
    subject: str, 
    template_name: str, 
    context: Dict[str, Any]
) -> bool:
    """Send notification email using template"""
    try:
        html_message = render_to_string(template_name, context)
        plain_message = strip_tags(html_message)
        
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[to_email],
            html_message=html_message,
            fail_silently=False,
        )
        return True
    except Exception as e:
        logger.error(f"Failed to send email to {to_email}: {e}")
        return False


def format_currency(amount: float, currency: str = 'AED') -> str:
    """Format currency amount"""
    return f"{currency} {amount:,.2f}"


def calculate_business_days(start_date: datetime, days: int) -> datetime:
    """Calculate business days excluding weekends"""
    current_date = start_date
    days_added = 0
    
    while days_added < days:
        current_date += timedelta(days=1)
        # Skip weekends (Saturday = 5, Sunday = 6)
        if current_date.weekday() < 5:
            days_added += 1
    
    return current_date


def sanitize_filename(filename: str) -> str:
    """Sanitize filename for safe storage"""
    # Remove or replace dangerous characters
    import re
    filename = re.sub(r'[^\w\s-.]', '', filename)
    filename = re.sub(r'[-\s]+', '-', filename)
    return filename.strip('-. ')


# Additional settings to add to base.py
"""
# Add these settings to your base.py file:

# Performance Monitoring
SLOW_REQUEST_THRESHOLD = 5.0  # seconds
MONITOR_DB_QUERIES = True
CACHE_PERFORMANCE_STATS = True

# Audit Logging
AUDIT_LOGGING_ENABLED = True
AUDIT_LOG_REQUEST_BODY = False  # Set to True for detailed logging
SENSITIVE_FIELDS = ['password', 'token', 'secret', 'api_key', 'credit_card']
AUDIT_EXCLUDED_PATHS = [
    '/admin/jsi18n/',
    '/static/',
    '/media/',
    '/health/',
    '/metrics/',
    '/favicon.ico'
]

# Security
RATE_LIMITING_ENABLED = True
BLOCKED_IPS = set()  # Add blocked IPs here
SUSPICIOUS_PATTERNS = ['wp-admin', 'phpmyadmin', '.env', 'config.php']

# Debug Logging
DEBUG_REQUEST_LOGGING = DEBUG

# Custom Exception Handler
REST_FRAMEWORK['DEFAULT_EXCEPTION_HANDLER'] = 'utils.exceptions.custom_exception_handler'

# Update middleware order
MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'utils.middleware.SecurityMiddleware',  # Add before other custom middleware
    'utils.middleware.PerformanceMiddleware',
    'utils.middleware.AuditMiddleware',
    # 'utils.middleware.RequestLoggingMiddleware',  # Only for debugging
]

# Logging configuration update
LOGGING['loggers']['audit'] = {
    'handlers': ['file'],
    'level': 'INFO',
    'propagate': False,
}
"""