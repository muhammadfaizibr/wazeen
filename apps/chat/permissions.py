from rest_framework import permissions
from django.shortcuts import get_object_or_404
from .models import ChatRoom


class ChatPermission(permissions.BasePermission):
    """
    Custom permission to check chat access rights.
    """
    
    def has_permission(self, request, view):
        """Check if user is authenticated"""
        return request.user and request.user.is_authenticated
    
    def has_object_permission(self, request, view, obj):
        """Check if user has access to specific chat objects"""
        
        # For ChatMessage objects, check room access
        if hasattr(obj, 'room'):
            return obj.room.can_user_access(request.user)
        
        # For ChatRoom objects, check direct access
        if hasattr(obj, 'can_user_access'):
            return obj.can_user_access(request.user)
        
        # For other objects related to chat, check via room_id in URL
        room_id = view.kwargs.get('room_id')
        if room_id:
            room = get_object_or_404(ChatRoom, id=room_id)
            return room.can_user_access(request.user)
        
        return False


class IsOwnerOrAdmin(permissions.BasePermission):
    """
    Custom permission to only allow owners of an object or admins to access it.
    """
    
    def has_object_permission(self, request, view, obj):
        # Admin users can access everything
        if request.user.role == 'admin':
            return True
        
        # For messages, check if user is the sender
        if hasattr(obj, 'sender'):
            return obj.sender == request.user
        
        # For other objects, check if user field exists
        if hasattr(obj, 'user'):
            return obj.user == request.user
        
        return False


class CanEditMessage(permissions.BasePermission):
    """
    Permission to check if user can edit a message.
    """
    
    def has_object_permission(self, request, view, obj):
        if hasattr(obj, 'can_user_edit'):
            return obj.can_user_edit(request.user)
        return False


class CanDeleteMessage(permissions.BasePermission):
    """
    Permission to check if user can delete a message.
    """
    
    def has_object_permission(self, request, view, obj):
        if hasattr(obj, 'can_user_delete'):
            return obj.can_user_delete(request.user)
        return False