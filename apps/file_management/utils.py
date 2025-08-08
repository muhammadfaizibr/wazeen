import os
import uuid
import secrets
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import UploadedFile
from django.conf import settings


def get_client_ip(request):
    """Get client IP address from request"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


def generate_download_token():
    """Generate secure download token"""
    return secrets.token_urlsafe(32)


def generate_secure_filename(original_filename):
    """Generate secure filename with UUID"""
    name, ext = os.path.splitext(original_filename)
    secure_name = f"{uuid.uuid4().hex}{ext.lower()}"
    return secure_name


class FileValidator:
    """File validation class"""
    
    def __init__(self, max_size=None, allowed_extensions=None):
        self.max_size = max_size or getattr(settings, 'FILE_UPLOAD_MAX_MEMORY_SIZE', 50 * 1024 * 1024)
        self.allowed_extensions = allowed_extensions or getattr(settings, 'ALLOWED_FILE_EXTENSIONS', [
            '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
            '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp',
            '.txt', '.zip', '.rar', '.7z'
        ])
    
    def __call__(self, file):
        self.validate_size(file)
        self.validate_extension(file)
        self.validate_content_type(file)
    
    def validate_size(self, file):
        """Validate file size"""
        if file.size > self.max_size:
            raise ValidationError(
                f"File size ({file.size} bytes) exceeds maximum allowed size "
                f"({self.max_size} bytes)."
            )
    
    def validate_extension(self, file):
        """Validate file extension"""
        _, ext = os.path.splitext(file.name)
        if ext.lower() not in self.allowed_extensions:
            raise ValidationError(
                f"File extension '{ext}' is not allowed. "
                f"Allowed extensions: {', '.join(self.allowed_extensions)}"
            )
    
    def validate_content_type(self, file):
        """Validate file content type"""
        dangerous_types = [
            'application/x-executable',
            'application/x-msdownload',
            'application/x-msdos-program',
            'application/x-msi',
            'application/x-bat',
            'application/x-sh',
            'text/x-script'
        ]
        
        if file.content_type in dangerous_types:
            raise ValidationError(
                f"File type '{file.content_type}' is not allowed for security reasons."
            )
