from rest_framework import serializers
from django.core.files.uploadedfile import UploadedFile
from apps.authentication.serializers import UserSerializer
from .models import File, FileCategory, FileDownload, FileShare
from django.conf import settings
from .utils import FileValidator, generate_secure_filename


class FileCategorySerializer(serializers.ModelSerializer):
    """File category serializer"""
    
    class Meta:
        model = FileCategory
        fields = ['id', 'name', 'name_ar', 'description', 'description_ar', 'color', 'is_active']


class FileUploadSerializer(serializers.ModelSerializer):
    """File upload serializer"""
    file = serializers.FileField(write_only=True, validators=[FileValidator()])
    
    class Meta:
        model = File
        fields = [
            'file', 'category', 'folder_path', 'tags'
        ]
        extra_kwargs = {
            'folder_path': {'required': False},
            'tags': {'required': False},
        }
    
    def validate_file(self, file):
        # Additional file validation
        if file.size > settings.FILE_UPLOAD_MAX_MEMORY_SIZE:
            raise serializers.ValidationError(
                f"File size exceeds maximum limit of {settings.FILE_UPLOAD_MAX_MEMORY_SIZE // 1048576} MB."
            )
        return file
    
    def create(self, validated_data):
        file_obj = validated_data.pop('file')
        request_obj = self.context['request_obj']
        user = self.context['request'].user
        
        # Generate file hash for deduplication
        file_content = file_obj.read()
        file_obj.seek(0)  # Reset file pointer
        
        file_hash = File().generate_hash(file_content)
        
        # Check for duplicate files in the same request
        existing_file = File.objects.filter(
            request=request_obj,
            file_hash=file_hash,
            is_deleted=False
        ).first()
        
        if existing_file:
            # Create new version instead of duplicate
            version_number = existing_file.versions.count() + 2
            stored_filename = generate_secure_filename(file_obj.name)
            
            # Save file
            file_path = self.save_file(file_obj, stored_filename)
            
            file_instance = File.objects.create(
                request=request_obj,
                uploaded_by=user,
                original_filename=file_obj.name,
                stored_filename=stored_filename,
                file_path=file_path,
                file_size=file_obj.size,
                mime_type=file_obj.content_type or 'application/octet-stream',
                file_hash=file_hash,
                version_number=version_number,
                parent_file=existing_file,
                **validated_data
            )
        else:
            stored_filename = generate_secure_filename(file_obj.name)
            file_path = self.save_file(file_obj, stored_filename)
            
            file_instance = File.objects.create(
                request=request_obj,
                uploaded_by=user,
                original_filename=file_obj.name,
                stored_filename=stored_filename,
                file_path=file_path,
                file_size=file_obj.size,
                mime_type=file_obj.content_type or 'application/octet-stream',
                file_hash=file_hash,
                **validated_data
            )
        
        # Trigger preview generation (async task)
        from .tasks import generate_file_preview
        generate_file_preview.delay(str(file_instance.id))
        
        return file_instance
    
    def save_file(self, file_obj, filename):
        """Save file to storage and return path"""
        from .storage import secure_file_storage
        return secure_file_storage.save_file(file_obj, filename)


class FileSerializer(serializers.ModelSerializer):
    """File detail serializer"""
    uploaded_by = UserSerializer(read_only=True)
    category = FileCategorySerializer(read_only=True)
    size_display = serializers.ReadOnlyField()
    file_extension = serializers.ReadOnlyField()
    is_image = serializers.ReadOnlyField()
    is_document = serializers.ReadOnlyField()
    download_url = serializers.SerializerMethodField()
    preview_url = serializers.SerializerMethodField()
    thumbnail_url = serializers.SerializerMethodField()
    download_count = serializers.SerializerMethodField()
    
    class Meta:
        model = File
        fields = [
            'id', 'original_filename', 'file_size', 'size_display', 'mime_type',
            'file_extension', 'is_image', 'is_document', 'uploaded_by', 'category',
            'folder_path', 'tags', 'version_number', 'parent_file', 'preview_status',
            'download_url', 'preview_url', 'thumbnail_url', 'download_count',
            'metadata', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'file_size', 'mime_type', 'uploaded_by', 'version_number',
            'parent_file', 'preview_status', 'created_at', 'updated_at'
        ]
    
    def get_download_url(self, obj):
        if self.context.get('request'):
            return obj.get_absolute_url()
        return None
    
    def get_preview_url(self, obj):
        if obj.preview_path and obj.preview_status == 'ready':
            return f"/api/files/{obj.id}/preview/"
        return None
    
    def get_thumbnail_url(self, obj):
        if obj.thumbnail_path:
            return f"/api/files/{obj.id}/thumbnail/"
        return None
    
    def get_download_count(self, obj):
        return obj.downloads.count()


class FileListSerializer(serializers.ModelSerializer):
    """File list serializer with minimal fields"""
    uploaded_by_name = serializers.CharField(source='uploaded_by.full_name', read_only=True)
    category_name = serializers.CharField(source='category.name', read_only=True)
    size_display = serializers.ReadOnlyField()
    file_extension = serializers.ReadOnlyField()
    is_image = serializers.ReadOnlyField()
    is_document = serializers.ReadOnlyField()
    download_count = serializers.SerializerMethodField()
    
    class Meta:
        model = File
        fields = [
            'id', 'original_filename', 'file_size', 'size_display', 'file_extension',
            'is_image', 'is_document', 'uploaded_by_name', 'category_name',
            'folder_path', 'tags', 'version_number', 'preview_status',
            'download_count', 'created_at'
        ]
    
    def get_download_count(self, obj):
        return obj.downloads.count()


class FileDownloadSerializer(serializers.ModelSerializer):
    """File download log serializer"""
    downloaded_by = UserSerializer(read_only=True)
    file_name = serializers.CharField(source='file.original_filename', read_only=True)
    
    class Meta:
        model = FileDownload
        fields = [
            'id', 'file_name', 'downloaded_by', 'ip_address',
            'user_agent', 'downloaded_at'
        ]


class FileShareSerializer(serializers.ModelSerializer):
    """File share serializer"""
    shared_by = UserSerializer(read_only=True)
    shared_with = UserSerializer(read_only=True)
    file_name = serializers.CharField(source='file.original_filename', read_only=True)
    share_url = serializers.SerializerMethodField()
    is_expired = serializers.ReadOnlyField()
    is_download_limit_reached = serializers.ReadOnlyField()
    
    class Meta:
        model = FileShare
        fields = [
            'id', 'file_name', 'shared_by', 'shared_with', 'share_token',
            'can_download', 'can_view_preview', 'expires_at', 'max_downloads',
            'download_count', 'is_active', 'share_url', 'is_expired',
            'is_download_limit_reached', 'created_at'
        ]
        read_only_fields = [
            'id', 'share_token', 'download_count', 'created_at'
        ]
    
    def get_share_url(self, obj):
        if self.context.get('request'):
            request = self.context['request']
            return request.build_absolute_uri(f'/api/files/share/{obj.share_token}/')
        return None
