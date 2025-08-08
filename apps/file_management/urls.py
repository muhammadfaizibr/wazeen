from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    FileCategoryListView, FileUploadView, FileListView, FileDetailView,
    download_file, preview_file, thumbnail_file,
    FileShareCreateView, FileShareListView, shared_file_access
)

app_name = 'file_management'

urlpatterns = [
    # Categories
    path('categories/', FileCategoryListView.as_view(), name='category-list'),
    
    # Files
    path('requests/<uuid:request_id>/files/', FileListView.as_view(), name='file-list'),
    path('requests/<uuid:request_id>/files/upload/', FileUploadView.as_view(), name='file-upload'),
    path('files/<uuid:pk>/', FileDetailView.as_view(), name='file-detail'),
    
    # File actions
    path('files/<uuid:file_id>/download/', download_file, name='file-download'),
    path('files/<uuid:file_id>/preview/', preview_file, name='file-preview'),
    path('files/<uuid:file_id>/thumbnail/', thumbnail_file, name='file-thumbnail'),
    
    # File sharing
    path('files/<uuid:file_id>/share/', FileShareCreateView.as_view(), name='file-share-create'),
    path('shares/', FileShareListView.as_view(), name='file-share-list'),
    path('share/<uuid:share_token>/', shared_file_access, name='shared-file-access'),
]