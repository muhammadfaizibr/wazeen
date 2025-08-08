import os
import shutil
from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.core.exceptions import SuspiciousOperation


class SecureFileStorage:
    """Secure file storage handler"""
    
    def __init__(self):
        self.base_path = getattr(settings, 'SECURE_FILE_ROOT', 'secure_files/')
        self.ensure_directory_exists(self.base_path)
    
    def ensure_directory_exists(self, path):
        """Ensure directory exists"""
        if not os.path.exists(path):
            os.makedirs(path, mode=0o755)
    
    def save_file(self, file_obj, filename):
        """Save file to secure location"""
        # Generate year/month subdirectory structure
        from datetime import datetime
        now = datetime.now()
        subdir = f"{now.year}/{now.month:02d}"
        
        full_dir = os.path.join(self.base_path, subdir)
        self.ensure_directory_exists(full_dir)
        
        file_path = os.path.join(full_dir, filename)
        
        # Ensure file doesn't already exist
        counter = 1
        original_path = file_path
        while os.path.exists(file_path):
            name, ext = os.path.splitext(original_path)
            file_path = f"{name}_{counter}{ext}"
            counter += 1
        
        # Save file
        with open(file_path, 'wb+') as destination:
            for chunk in file_obj.chunks():
                destination.write(chunk)
        
        # Return relative path from base
        return os.path.relpath(file_path, self.base_path)
    
    def get_file_path(self, relative_path):
        """Get absolute file path"""
        file_path = os.path.join(self.base_path, relative_path)
        
        # Security check: ensure path is within base directory
        if not os.path.commonpath([self.base_path, file_path]) == self.base_path:
            raise SuspiciousOperation("File path is outside secure directory")
        
        return file_path
    
    def delete_file(self, relative_path):
        """Delete file"""
        try:
            file_path = self.get_file_path(relative_path)
            if os.path.exists(file_path):
                os.remove(file_path)
                return True
        except (OSError, SuspiciousOperation):
            pass
        return False


# Global storage instance
secure_file_storage = SecureFileStorage()