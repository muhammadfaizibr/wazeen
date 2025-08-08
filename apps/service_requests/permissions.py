from rest_framework import permissions
from .models import ServiceRequest


class ServiceRequestPermission(permissions.BasePermission):
    """
    Custom permission for service requests
    """
    
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated
    
    def has_object_permission(self, request, view, obj):
        user = request.user
        
        # Admin has full access
        if user.role == 'admin':
            return True
        
        # Client can only access their own requests
        if user.role == 'client':
            return obj.client == user
        
        # Accountant can access assigned requests or unassigned ones
        if user.role == 'accountant':
            return obj.accountant == user or obj.accountant is None
        
        return False


class RequestNotePermission(permissions.BasePermission):
    """
    Custom permission for request notes
    """
    
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated
    
    def has_object_permission(self, request, view, obj):
        user = request.user
        service_request = obj.request
        
        # Admin has full access
        if user.role == 'admin':
            return True
        
        # Check if user has access to the parent request
        if user.role == 'client':
            if service_request.client != user:
                return False
            # Clients can't see internal notes
            if obj.is_internal:
                return False
        
        elif user.role == 'accountant':
            if service_request.accountant != user:
                return False
        
        return True
