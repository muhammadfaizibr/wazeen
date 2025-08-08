from rest_framework import permissions


class FilePermission(permissions.BasePermission):
    """Custom permission for file operations"""
    
    def has_object_permission(self, request, view, obj):
        # Users can always view files they uploaded
        if obj.uploaded_by == request.user:
            return True
        
        # Check if user has permission via service request
        if hasattr(obj, 'request'):
            service_request = obj.request
            
            if request.method in permissions.SAFE_METHODS:
                return service_request.can_user_view_files(request.user)
            else:
                return service_request.can_user_manage_files(request.user)
        
        return False