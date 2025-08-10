import jwt
from django.conf import settings
from django.shortcuts import get_object_or_404
from django.http import HttpResponse, Http404, FileResponse
from django.utils import timezone
from django.db.models import Q
from rest_framework import generics, status, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from django.core.exceptions import PermissionDenied
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_control

from apps.service_requests.models import ServiceRequest
from .models import File, FileCategory, FileDownload, FileShare
from .serializers import (
    FileUploadSerializer, FileSerializer, FileListSerializer,
    FileCategorySerializer, FileDownloadSerializer, FileShareSerializer
)
from .filters import FileFilter
from .permissions import FilePermission
from .utils import get_client_ip, generate_download_token


class FileCategoryListView(generics.ListCreateAPIView):
    """List and create file categories"""
    queryset = FileCategory.objects.filter(is_active=True)
    serializer_class = FileCategorySerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        queryset = super().get_queryset()
        if self.request.query_params.get('all'):
            return FileCategory.objects.all()
        return queryset


class FileUploadView(generics.CreateAPIView):
    """Upload files to a service request"""
    serializer_class = FileUploadSerializer
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [IsAuthenticated]
    
    def get_serializer_context(self):
        context = super().get_serializer_context()
        request_id = self.kwargs.get('request_id')
        context['request_obj'] = get_object_or_404(ServiceRequest, id=request_id)
        return context
    
    def perform_create(self, serializer):
        request_obj = self.get_serializer_context()['request_obj']
        
        # Check if user has permission to upload files to this request
        if not request_obj.can_user_upload_files(self.request.user):
            raise PermissionDenied("You don't have permission to upload files to this request.")
        
        serializer.save()


class FileListView(generics.ListAPIView):
    """List files for a service request"""
    serializer_class = FileListSerializer
    permission_classes = [IsAuthenticated, FilePermission]
    filter_backends = [DjangoFilterBackend]
    filterset_class = FileFilter
    
    def get_queryset(self):
        request_id = self.kwargs.get('request_id')
        request_obj = get_object_or_404(ServiceRequest, id=request_id)
        
        # Check if user has permission to view files
        if not request_obj.can_user_view_files(self.request.user):
            raise PermissionDenied("You don't have permission to view files for this request.")
        
        return File.objects.filter(
            request=request_obj,
            is_deleted=False
        ).select_related('uploaded_by', 'category')


class FileDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Retrieve, update or delete a specific file"""
    serializer_class = FileSerializer
    permission_classes = [IsAuthenticated, FilePermission]
    
    def get_queryset(self):
        return File.objects.filter(is_deleted=False).select_related(
            'uploaded_by', 'category', 'parent_file'
        ).prefetch_related('versions')
    
    def perform_destroy(self, instance):
        # Soft delete
        instance.is_deleted = True
        instance.save()

@api_view(['GET'])
@permission_classes([IsAuthenticated])
@cache_control(max_age=3600)
def download_file(request, file_id):
    """Download a file"""
    print("=== DOWNLOAD_FILE VIEW STARTED ===")
    
    file_obj = get_object_or_404(File, id=file_id, is_deleted=False)
    print(f"Downloading file: {file_obj.original_filename} (ID: {file_obj.id})"
          f" for request: {file_obj.request.title} (ID: {file_obj.request.id})")

    # Log download
    download_record = FileDownload.objects.create(
        file=file_obj,
        downloaded_by=request.user if request.user.is_authenticated else None,
        ip_address=get_client_ip(request),
        user_agent=request.META.get('HTTP_USER_AGENT', ''),
        download_token=generate_download_token()
    )
    print(f"Download record created: {download_record.id}")

    # try:
    from .storage import secure_file_storage
    file_path = secure_file_storage.get_file_path(file_obj.stored_filename)
    print(f"File path resolved: {file_path}")
    
    # Check if file actually exists
    import os
    print(f"File exists on disk: {os.path.exists(file_path)}")
    
    response = FileResponse(
        open(file_path, 'rb'),
        content_type=file_obj.mime_type,
        as_attachment=True,
        filename=file_obj.original_filename
    )

    response['Content-Length'] = file_obj.file_size
    response['Content-Disposition'] = f'attachment; filename="{file_obj.original_filename}"'
    
    print(f"Response created successfully. Status: {response.status_code}")
    print("=== DOWNLOAD_FILE VIEW COMPLETED ===")
    
    return response

    # except FileNotFoundError as e:
    #     print(f"FileNotFoundError: {e}")
    #     raise Http404("File not found on disk.")
    # except Exception as e:
    #     print(f"Unexpected error: {e}")
    #     raise

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def preview_file(request, file_id):
    """Preview a file (if preview is available)"""
    file_obj = get_object_or_404(File, id=file_id, is_deleted=False)
    
    # Check permissions
    if not file_obj.request.can_user_view_files(request.user):
        raise PermissionDenied("You don't have permission to preview this file.")
    
    if file_obj.preview_status != 'ready' or not file_obj.preview_path:
        return Response(
            {"error": "Preview not available for this file."},
            status=status.HTTP_404_NOT_FOUND
        )
    
    try:
        from .storage import secure_file_storage
        preview_path = secure_file_storage.get_file_path(file_obj.preview_path)
        
        return FileResponse(
            open(preview_path, 'rb'),
            content_type='application/pdf'  # Assuming previews are PDFs
        )
        
    except FileNotFoundError:
        raise Http404("Preview file not found on disk.")


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def thumbnail_file(request, file_id):
    """Get file thumbnail"""
    file_obj = get_object_or_404(File, id=file_id, is_deleted=False)
    
    # Check permissions
    if not file_obj.request.can_user_view_files(request.user):
        raise PermissionDenied("You don't have permission to view this file.")
    
    if not file_obj.thumbnail_path:
        return Response(
            {"error": "Thumbnail not available for this file."},
            status=status.HTTP_404_NOT_FOUND
        )
    
    try:
        from .storage import secure_file_storage
        thumbnail_path = secure_file_storage.get_file_path(file_obj.thumbnail_path)
        
        return FileResponse(
            open(thumbnail_path, 'rb'),
            content_type='image/jpeg'
        )
        
    except FileNotFoundError:
        raise Http404("Thumbnail not found on disk.")


class FileShareCreateView(generics.CreateAPIView):
    """Create file share"""
    serializer_class = FileShareSerializer
    permission_classes = [IsAuthenticated]
    
    def perform_create(self, serializer):
        file_id = self.kwargs.get('file_id')
        file_obj = get_object_or_404(File, id=file_id, is_deleted=False)
        
        # Check permissions
        if not file_obj.request.can_user_share_files(self.request.user):
            raise PermissionDenied("You don't have permission to share this file.")
        
        serializer.save(file=file_obj, shared_by=self.request.user)


class FileShareListView(generics.ListAPIView):
    """List file shares"""
    serializer_class = FileShareSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return FileShare.objects.filter(
            shared_by=self.request.user,
            is_active=True
        ).select_related('file', 'shared_with')


@api_view(['GET'])
def shared_file_access(request, share_token):
    """Access shared file via token"""
    share = get_object_or_404(
        FileShare,
        share_token=share_token,
        is_active=True
    )
    
    # Check if share is expired
    if share.is_expired:
        return Response(
            {"error": "This share link has expired."},
            status=status.HTTP_410_GONE
        )
    
    # Check download limit
    if share.is_download_limit_reached:
        return Response(
            {"error": "Download limit reached for this share link."},
            status=status.HTTP_429_TOO_MANY_REQUESTS
        )
    
    # If this is a download request
    if request.query_params.get('action') == 'download':
        if not share.can_download:
            return Response(
                {"error": "Download not allowed for this share."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Increment download count
        share.download_count += 1
        share.save()
        
        # Log download (for anonymous/external users)
        FileDownload.objects.create(
            file=share.file,
            downloaded_by=request.user if request.user.is_authenticated else None,
            ip_address=get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            download_token=str(share.share_token)
        )
        
        try:
            from .storage import secure_file_storage
            file_path = secure_file_storage.get_file_path(share.file.stored_filename)
            
            return FileResponse(
                open(file_path, 'rb'),
                content_type=share.file.mime_type,
                as_attachment=True,
                filename=share.file.original_filename
            )
            
        except FileNotFoundError:
            raise Http404("File not found on disk.")
    
    # Return file info for preview/display
    serializer = FileSerializer(share.file, context={'request': request})
    return Response({
        'file': serializer.data,
        'share_info': {
            'can_download': share.can_download,
            'can_view_preview': share.can_view_preview,
            'expires_at': share.expires_at,
            'downloads_remaining': (
                share.max_downloads - share.download_count
                if share.max_downloads else None
            )
        }
    })