from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from .models import File, FileCategory, FileDownload, FileShare


@admin.register(FileCategory)
class FileCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'name_ar', 'color_display', 'is_active', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['name', 'name_ar', 'description']
    list_editable = ['is_active']
    
    def color_display(self, obj):
        return format_html(
            '<span style="background-color: {}; padding: 2px 10px; border-radius: 3px; color: white;">{}</span>',
            obj.color,
            obj.color
        )
    color_display.short_description = 'Color'


@admin.register(File)
class FileAdmin(admin.ModelAdmin):
    list_display = [
        'original_filename', 'request_title', 'uploaded_by_name', 
        'size_display', 'category', 'preview_status', 'is_deleted', 'created_at'
    ]
    list_filter = [
        'mime_type', 'category', 'preview_status', 'is_deleted', 
        'is_virus_scanned', 'created_at'
    ]
    search_fields = ['original_filename', 'request__title', 'uploaded_by__email']
    readonly_fields = [
        'id', 'file_hash', 'file_size', 'mime_type', 'stored_filename', 
        'file_path', 'preview_status', 'created_at', 'updated_at'
    ]
    raw_id_fields = ['request', 'uploaded_by', 'parent_file']
    list_per_page = 25
    
    fieldsets = (
        ('File Information', {
            'fields': ('id', 'original_filename', 'stored_filename', 'file_path', 
                      'file_size', 'mime_type', 'file_hash')
        }),
        ('Request & User', {
            'fields': ('request', 'uploaded_by')
        }),
        ('Organization', {
            'fields': ('category', 'folder_path', 'tags')
        }),
        ('Versioning', {
            'fields': ('version_number', 'parent_file')
        }),
        ('Preview & Processing', {
            'fields': ('preview_status', 'preview_path', 'thumbnail_path')
        }),
        ('Security', {
            'fields': ('is_virus_scanned', 'virus_scan_result')
        }),
        ('Status & Metadata', {
            'fields': ('is_deleted', 'metadata')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at')
        }),
    )
    
    def request_title(self, obj):
        return obj.request.title[:50] + '...' if len(obj.request.title) > 50 else obj.request.title
    request_title.short_description = 'Request'
    
    def uploaded_by_name(self, obj):
        return obj.uploaded_by.full_name
    uploaded_by_name.short_description = 'Uploaded By'
    
    actions = ['mark_as_deleted', 'restore_deleted', 'generate_previews']