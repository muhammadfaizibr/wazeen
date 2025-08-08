from rest_framework import permissions

class IsOwnerOrAdmin(permissions.BasePermission):
    """
    Custom permission to only allow owners of an object or admins to edit it.
    """
    
    def has_object_permission(self, request, view, obj):
        # Admin has all permissions
        if request.user.role == 'admin':
            return True
        
        # Owner has all permissions on their own objects
        if hasattr(obj, 'user'):
            return obj.user == request.user
        
        return obj == request.user


class IsAdminUser(permissions.BasePermission):
    """
    Custom permission to only allow admin users.
    """
    
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.role == 'admin'


class IsAccountantUser(permissions.BasePermission):
    """
    Custom permission to only allow accountant users.
    """
    
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.role == 'accountant'


class IsClientUser(permissions.BasePermission):
    """
    Custom permission to only allow client users.
    """
    
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.role == 'client'