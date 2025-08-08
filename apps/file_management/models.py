import uuid
import hashlib
import os
from django.db import models
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.core.validators import FileExtensionValidator
from django.conf import settings

User = get_user_model()


class FileCategory(models.Model):
    """File categories for organization"""
    name = models.CharField(max_length=100)
    name_ar = models.CharField(max_length=100, blank=True)
    description = models.TextField(blank=True)
    description_ar = models.TextField(blank=True)
    color = models.CharField(max_length=7, default='#007bff', help_text="Hex color code")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'file_categories'
        verbose_name_plural = 'File Categories'
    
    def __str__(self):
        return self.name


class File(models.Model):
    """File model for document management"""
    
    PREVIEW_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('ready', 'Ready'),
        ('failed', 'Failed'),
        ('not_supported', 'Not Supported'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    request = models.ForeignKey(
        'service_requests.ServiceRequest', 
        on_delete=models.CASCADE, 
        related_name='files'
    )
    uploaded_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='uploaded_files')
    
    # File information
    original_filename = models.CharField(max_length=255)
    stored_filename = models.CharField(max_length=255, unique=True)
    file_path = models.CharField(max_length=1000)
    file_size = models.BigIntegerField()  # Size in bytes
    mime_type = models.CharField(max_length=100)
    file_hash = models.CharField(max_length=64, db_index=True)  # SHA-256 hash
    
    # Organization
    category = models.ForeignKey(FileCategory, on_delete=models.SET_NULL, null=True, blank=True)
    folder_path = models.CharField(max_length=500, default='/')
    tags = models.JSONField(default=list, blank=True)
    
    # Versioning
    version_number = models.IntegerField(default=1)
    parent_file = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='versions')
    
    # Preview and processing
    preview_status = models.CharField(
        max_length=20, 
        choices=PREVIEW_STATUS_CHOICES, 
        default='pending'
    )
    preview_path = models.CharField(max_length=1000, blank=True)
    thumbnail_path = models.CharField(max_length=1000, blank=True)
    
    # Status
    is_deleted = models.BooleanField(default=False)
    is_virus_scanned = models.BooleanField(default=False)
    virus_scan_result = models.CharField(max_length=20, blank=True)
    
    # Metadata
    metadata = models.JSONField(default=dict, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'files'
        indexes = [
            models.Index(fields=['request']),
            models.Index(fields=['uploaded_by']),
            models.Index(fields=['file_hash']),
            models.Index(fields=['created_at']),
            models.Index(fields=['is_deleted']),
        ]
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.original_filename} - {self.request.title}"
    
    @property
    def file_extension(self):
        return os.path.splitext(self.original_filename)[1].lower()
    
    @property
    def size_display(self):
        """Return human readable file size"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if self.file_size < 1024.0:
                return f"{self.file_size:.1f} {unit}"
            self.file_size /= 1024.0
        return f"{self.file_size:.1f} TB"
    
    @property
    def is_image(self):
        image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']
        return self.file_extension in image_extensions
    
    @property
    def is_document(self):
        doc_extensions = ['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.txt']
        return self.file_extension in doc_extensions
    
    def get_absolute_url(self):
        return f"/api/files/{self.id}/download/"
    
    def generate_hash(self, file_content):
        """Generate SHA-256 hash of file content"""
        return hashlib.sha256(file_content).hexdigest()


class FileDownload(models.Model):
    """Track file downloads for audit purposes"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    file = models.ForeignKey(File, on_delete=models.CASCADE, related_name='downloads')
    downloaded_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='file_downloads')
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField(blank=True)
    download_token = models.CharField(max_length=255, blank=True)
    downloaded_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'file_downloads'
        indexes = [
            models.Index(fields=['file']),
            models.Index(fields=['downloaded_by']),
            models.Index(fields=['downloaded_at']),
        ]
        ordering = ['-downloaded_at']
    
    def __str__(self):
        return f"{self.file.original_filename} downloaded by {self.downloaded_by.full_name}"


class FileShare(models.Model):
    """Share files with specific users or generate public links"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    file = models.ForeignKey(File, on_delete=models.CASCADE, related_name='shares')
    shared_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='shared_files')
    shared_with = models.ForeignKey(
        User, on_delete=models.CASCADE, 
        null=True, blank=True, 
        related_name='received_files'
    )
    share_token = models.UUIDField(default=uuid.uuid4, unique=True)
    
    # Permissions
    can_download = models.BooleanField(default=True)
    can_view_preview = models.BooleanField(default=True)
    
    # Expiration
    expires_at = models.DateTimeField(null=True, blank=True)
    max_downloads = models.IntegerField(null=True, blank=True)
    download_count = models.IntegerField(default=0)
    
    # Status
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'file_shares'
        indexes = [
            models.Index(fields=['share_token']),
            models.Index(fields=['expires_at']),
        ]
    
    def __str__(self):
        return f"Share: {self.file.original_filename}"
    
    @property
    def is_expired(self):
        if self.expires_at:
            return timezone.now() > self.expires_at
        return False
    
    @property
    def is_download_limit_reached(self):
        if self.max_downloads:
            return self.download_count >= self.max_downloads
        return False
