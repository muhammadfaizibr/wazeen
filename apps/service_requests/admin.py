from django.contrib import admin
from django.utils.html import format_html
from .models import (
    ServiceRequest, 
    ServiceRequestCategory, 
    RequestNote, 
    RequestAssignment,
    RequestStatusHistory
)


@admin.register(ServiceRequestCategory)
class ServiceRequestCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'name_ar', 'is_active', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['name', 'name_ar']
    list_editable = ['is_active']


class RequestNoteInline(admin.TabularInline):
    model = RequestNote
    extra = 0
    fields = ['author', 'content', 'is_internal', 'created_at']
    readonly_fields = ['created_at']


class RequestAssignmentInline(admin.TabularInline):
    model = RequestAssignment
    extra = 0
    fields = ['from_accountant', 'to_accountant', 'assigned_by', 'reason', 'assigned_at']
    readonly_fields = ['assigned_at']


@admin.register(ServiceRequest)
class ServiceRequestAdmin(admin.ModelAdmin):
    list_display = [
        'title', 'client', 'accountant', 'status', 'priority',
        'category', 'due_date', 'is_overdue_display', 'created_at'
    ]
    list_filter = [
        'status', 'priority', 'category', 'created_at',
        'due_date', 'client__role'
    ]
    search_fields = [
        'title', 'description', 'client__first_name', 
        'client__last_name', 'client__email'
    ]
    date_hierarchy = 'created_at'
    inlines = [RequestNoteInline, RequestAssignmentInline]
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('title', 'description', 'category', 'client')
        }),
        ('Assignment', {
            'fields': ('accountant', 'status', 'priority')
        }),
        ('Timing', {
            'fields': ('due_date', 'estimated_hours', 'actual_hours')
        }),
        ('Additional', {
            'fields': ('tags', 'custom_fields'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': (
                'created_at', 'updated_at', 'started_at',
                'completed_at', 'closed_at'
            ),
            'classes': ('collapse',)
        })
    )
    
    readonly_fields = [
        'created_at', 'updated_at', 'started_at',
        'completed_at', 'closed_at'
    ]
    
    def is_overdue_display(self, obj):
        if obj.is_overdue:
            return format_html(
                '<span style="color: red; font-weight: bold;">Overdue</span>'
            )
        return 'No'
    is_overdue_display.short_description = 'Overdue'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'client', 'accountant', 'category'
        )


@admin.register(RequestNote)
class RequestNoteAdmin(admin.ModelAdmin):
    list_display = ['request', 'author', 'is_internal', 'created_at']
    list_filter = ['is_internal', 'created_at', 'author__role']
    search_fields = ['content', 'request__title', 'author__email']
    date_hierarchy = 'created_at'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'request', 'author'
        )


@admin.register(RequestAssignment)
class RequestAssignmentAdmin(admin.ModelAdmin):
    list_display = [
        'request', 'from_accountant', 'to_accountant',
        'assigned_by', 'assigned_at'
    ]
    list_filter = ['assigned_at', 'to_accountant']
    search_fields = ['request__title', 'reason']
    date_hierarchy = 'assigned_at'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'request', 'from_accountant', 'to_accountant', 'assigned_by'
        )


@admin.register(RequestStatusHistory)
class RequestStatusHistoryAdmin(admin.ModelAdmin):
    list_display = ['request', 'from_status', 'to_status', 'changed_by', 'changed_at']
    list_filter = ['from_status', 'to_status', 'changed_at']
    search_fields = ['request__title', 'reason']
    date_hierarchy = 'changed_at'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'request', 'changed_by'
        )