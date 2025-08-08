from rest_framework import permissions
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from functools import wraps

User = get_user_model()


class IsOwnerOrReadOnly(permissions.BasePermission):
    """
    Custom permission to only allow owners of an object to edit it.
    Read permissions are allowed for authenticated users.
    """
    
    def has_object_permission(self, request, view, obj):
        # Read permissions are allowed to any authenticated user
        if request.method in permissions.SAFE_METHODS:
            return request.user.is_authenticated
        
        # Write permissions are only allowed to the owner of the object
        if hasattr(obj, 'user'):
            return obj.user == request.user
        elif hasattr(obj, 'client'):
            return obj.client == request.user
        elif hasattr(obj, 'created_by'):
            return obj.created_by == request.user
        
        return obj == request.user


class IsOwnerOrAdmin(permissions.BasePermission):
    """
    Custom permission to only allow owners of an object or admins to access it.
    """
    
    def has_object_permission(self, request, view, obj):
        # Admin has all permissions
        if request.user.role == 'admin':
            return True
        
        # Owner has all permissions on their own objects
        if hasattr(obj, 'user'):
            return obj.user == request.user
        elif hasattr(obj, 'client'):
            return obj.client == request.user
        elif hasattr(obj, 'created_by'):
            return obj.created_by == request.user
        
        return obj == request.user


class IsAdminUser(permissions.BasePermission):
    """
    Permission to only allow admin users.
    """
    
    def has_permission(self, request, view):
        return (
            request.user and 
            request.user.is_authenticated and 
            request.user.role == 'admin'
        )


class IsAccountantUser(permissions.BasePermission):
    """
    Permission to only allow accountant users.
    """
    
    def has_permission(self, request, view):
        return (
            request.user and 
            request.user.is_authenticated and 
            request.user.role == 'accountant'
        )


class IsClientUser(permissions.BasePermission):
    """
    Permission to only allow client users.
    """
    
    def has_permission(self, request, view):
        return (
            request.user and 
            request.user.is_authenticated and 
            request.user.role == 'client'
        )


class IsAdminOrAccountant(permissions.BasePermission):
    """
    Permission to allow admin or accountant users.
    """
    
    def has_permission(self, request, view):
        return (
            request.user and 
            request.user.is_authenticated and 
            request.user.role in ['admin', 'accountant']
        )


class IsAdminOrOwner(permissions.BasePermission):
    """
    Permission to allow admin users or object owners.
    """
    
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated
    
    def has_object_permission(self, request, view, obj):
        # Admin has all permissions
        if request.user.role == 'admin':
            return True
        
        # Check ownership
        if hasattr(obj, 'user'):
            return obj.user == request.user
        elif hasattr(obj, 'client'):
            return obj.client == request.user
        elif hasattr(obj, 'created_by'):
            return obj.created_by == request.user
        
        return obj == request.user


class IsVerifiedUser(permissions.BasePermission):
    """
    Permission to only allow email verified users.
    """
    
    def has_permission(self, request, view):
        return (
            request.user and 
            request.user.is_authenticated and 
            request.user.email_verified
        )


class ReadOnlyPermission(permissions.BasePermission):
    """
    Permission that only allows read-only access.
    """
    
    def has_permission(self, request, view):
        return request.method in permissions.SAFE_METHODS


class ServiceRequestPermission(permissions.BasePermission):
    """
    Custom permission for service requests based on user role and ownership.
    """
    
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated
    
    def has_object_permission(self, request, view, obj):
        user = request.user
        
        # Admin can access everything
        if user.role == 'admin':
            return True
        
        # Client can only access their own requests
        if user.role == 'client':
            return obj.client == user
        
        # Accountant can access assigned requests or unassigned ones
        if user.role == 'accountant':
            return obj.accountant == user or obj.accountant is None
        
        return False


class FilePermission(permissions.BasePermission):
    """
    Custom permission for file operations based on service request access.
    """
    
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated
    
    def has_object_permission(self, request, view, obj):
        user = request.user
        service_request = obj.request
        
        # Admin can access everything
        if user.role == 'admin':
            return True
        
        # Client can access files from their own requests
        if user.role == 'client':
            return service_request.client == user
        
        # Accountant can access files from assigned or unassigned requests
        if user.role == 'accountant':
            return service_request.accountant == user or service_request.accountant is None
        
        return False


class RoleBasedPermission(permissions.BasePermission):
    """
    Dynamic role-based permission class.
    Usage: permission_classes = [RoleBasedPermission(['admin', 'accountant'])]
    """
    
    def __init__(self, allowed_roles):
        self.allowed_roles = allowed_roles
    
    def __call__(self):
        # This allows the class to be used as a permission class
        return self
    
    def has_permission(self, request, view):
        return (
            request.user and 
            request.user.is_authenticated and 
            request.user.role in self.allowed_roles
        )


class ConditionalPermission(permissions.BasePermission):
    """
    Permission that applies different logic based on HTTP method.
    """
    
    read_permissions = []  # Override in subclasses
    write_permissions = []  # Override in subclasses
    
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return all(perm().has_permission(request, view) for perm in self.read_permissions)
        else:
            return all(perm().has_permission(request, view) for perm in self.write_permissions)
    
    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return all(perm().has_object_permission(request, view, obj) for perm in self.read_permissions)
        else:
            return all(perm().has_object_permission(request, view, obj) for perm in self.write_permissions)


class TimeBasedPermission(permissions.BasePermission):
    """
    Permission that restricts access based on time constraints.
    """
    
    def has_permission(self, request, view):
        from django.utils import timezone
        from datetime import time
        
        if not (request.user and request.user.is_authenticated):
            return False
        
        # Example: Only allow access during business hours (9 AM - 6 PM)
        current_time = timezone.localtime().time()
        start_time = time(9, 0)  # 9 AM
        end_time = time(18, 0)   # 6 PM
        
        # Admin users can access anytime
        if request.user.role == 'admin':
            return True
        
        return start_time <= current_time <= end_time


class IPWhitelistPermission(permissions.BasePermission):
    """
    Permission that restricts access based on IP address.
    """
    
    allowed_ips = []  # Override in settings or subclass
    
    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        
        # Get client IP
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        
        # Admin users bypass IP restrictions
        if request.user.role == 'admin':
            return True
        
        return ip in self.allowed_ips


# Decorator functions for view-level permissions
def require_role(allowed_roles):
    """
    Decorator to require specific roles for view access.
    Usage: @require_role(['admin', 'accountant'])
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                raise PermissionDenied("Authentication required")
            
            if request.user.role not in allowed_roles:
                raise PermissionDenied(f"Role '{request.user.role}' not allowed. Required: {allowed_roles}")
            
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def require_verified_email(view_func):
    """
    Decorator to require verified email for view access.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            raise PermissionDenied("Authentication required")
        
        if not request.user.email_verified:
            raise PermissionDenied("Email verification required")
        
        return view_func(request, *args, **kwargs)
    return wrapper


def require_ownership(owner_field='user'):
    """
    Decorator to require object ownership for view access.
    Usage: @require_ownership('client')
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            # This would need to be implemented based on your specific use case
            # as it requires access to the object being accessed
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


class PermissionMixin:
    """
    Mixin for views that provides common permission checking methods.
    """
    
    def check_object_permissions(self, request, obj):
        """
        Check if user has permission to access the object.
        """
        super().check_object_permissions(request, obj)
    
    def is_owner(self, request, obj):
        """
        Check if user is the owner of the object.
        """
        if hasattr(obj, 'user'):
            return obj.user == request.user
        elif hasattr(obj, 'client'):
            return obj.client == request.user
        elif hasattr(obj, 'created_by'):
            return obj.created_by == request.user
        return obj == request.user
    
    def is_admin(self, request):
        """
        Check if user is an admin.
        """
        return request.user.is_authenticated and request.user.role == 'admin'
    
    def is_accountant(self, request):
        """
        Check if user is an accountant.
        """
        return request.user.is_authenticated and request.user.role == 'accountant'
    
    def is_client(self, request):
        """
        Check if user is a client.
        """
        return request.user.is_authenticated and request.user.role == 'client'
    
    def has_role(self, request, roles):
        """
        Check if user has one of the specified roles.
        """
        if isinstance(roles, str):
            roles = [roles]
        return request.user.is_authenticated and request.user.role in roles