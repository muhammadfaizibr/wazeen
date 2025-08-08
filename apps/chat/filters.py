# apps/chat/filters.py
import django_filters
from django.utils import timezone
from datetime import timedelta
from .models import ChatMessage, ChatRoom
from django.db import models


class ChatMessageFilter(django_filters.FilterSet):
    """Filter for chat messages"""
    
    # Date range filters
    date_from = django_filters.DateTimeFilter(field_name='created_at', lookup_expr='gte')
    date_to = django_filters.DateTimeFilter(field_name='created_at', lookup_expr='lte')
    
    # Message type filter
    message_type = django_filters.MultipleChoiceFilter(
        choices=ChatMessage.MESSAGE_TYPES,
        field_name='message_type'
    )
    
    # Sender filter
    sender = django_filters.UUIDFilter(field_name='sender__id')
    sender_role = django_filters.ChoiceFilter(
        field_name='sender__role',
        choices=[
            ('admin', 'Admin'),
            ('accountant', 'Accountant'),
            ('client', 'Client'),
        ]
    )
    
    # Content search
    search = django_filters.CharFilter(method='filter_search')
    
    # File messages only
    has_file = django_filters.BooleanFilter(method='filter_has_file')
    
    # Read status
    is_unread = django_filters.BooleanFilter(method='filter_unread')
    
    # Time range shortcuts
    time_range = django_filters.ChoiceFilter(
        method='filter_time_range',
        choices=[
            ('today', 'Today'),
            ('yesterday', 'Yesterday'),
            ('this_week', 'This Week'),
            ('last_week', 'Last Week'),
            ('this_month', 'This Month'),
            ('last_month', 'Last Month'),
        ]
    )
    
    class Meta:
        model = ChatMessage
        fields = [
            'message_type', 'is_read', 'is_edited',
            'date_from', 'date_to', 'sender', 'sender_role',
            'search', 'has_file', 'is_unread', 'time_range'
        ]
    
    def filter_search(self, queryset, name, value):
        """Full-text search in message content"""
        if value:
            return queryset.filter(content__icontains=value)
        return queryset
    
    def filter_has_file(self, queryset, name, value):
        """Filter messages that have file attachments"""
        if value is True:
            return queryset.filter(file__isnull=False)
        elif value is False:
            return queryset.filter(file__isnull=True)
        return queryset
    
    def filter_unread(self, queryset, name, value):
        """Filter unread messages for current user"""
        if value and hasattr(self.request, 'user') and self.request.user.is_authenticated:
            return queryset.filter(is_read=False).exclude(sender=self.request.user)
        return queryset
    
    def filter_time_range(self, queryset, name, value):
        """Filter by predefined time ranges"""
        now = timezone.now()
        
        if value == 'today':
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            return queryset.filter(created_at__gte=start)
        
        elif value == 'yesterday':
            yesterday = now - timedelta(days=1)
            start = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
            end = yesterday.replace(hour=23, minute=59, second=59, microsecond=999999)
            return queryset.filter(created_at__gte=start, created_at__lte=end)
        
        elif value == 'this_week':
            start = now - timedelta(days=now.weekday())
            start = start.replace(hour=0, minute=0, second=0, microsecond=0)
            return queryset.filter(created_at__gte=start)
        
        elif value == 'last_week':
            end = now - timedelta(days=now.weekday())
            end = end.replace(hour=23, minute=59, second=59, microsecond=999999)
            start = end - timedelta(days=6)
            start = start.replace(hour=0, minute=0, second=0, microsecond=0)
            return queryset.filter(created_at__gte=start, created_at__lte=end)
        
        elif value == 'this_month':
            start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            return queryset.filter(created_at__gte=start)
        
        elif value == 'last_month':
            # First day of current month
            first_current = now.replace(day=1)
            # Last day of previous month
            end = first_current - timedelta(days=1)
            end = end.replace(hour=23, minute=59, second=59, microsecond=999999)
            # First day of previous month
            start = end.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            return queryset.filter(created_at__gte=start, created_at__lte=end)
        
        return queryset


class ChatRoomFilter(django_filters.FilterSet):
    """Filter for chat rooms"""
    
    # Activity status
    is_active = django_filters.BooleanFilter()
    
    # Request status
    request_status = django_filters.ChoiceFilter(
        field_name='request__status',
        choices=[
            ('new', 'New'),
            ('in_progress', 'In Progress'),
            ('review', 'Under Review'),
            ('completed', 'Completed'),
            ('closed', 'Closed'),
        ]
    )
    
    # Request priority
    request_priority = django_filters.ChoiceFilter(
        field_name='request__priority',
        choices=[
            ('low', 'Low'),
            ('medium', 'Medium'),
            ('high', 'High'),
            ('urgent', 'Urgent'),
        ]
    )
    
    # Has unread messages
    has_unread = django_filters.BooleanFilter(method='filter_has_unread')
    
    # Recently active
    recently_active = django_filters.BooleanFilter(method='filter_recently_active')
    
    # Search in request title/description
    search = django_filters.CharFilter(method='filter_search')
    
    class Meta:
        model = ChatRoom
        fields = [
            'is_active', 'request_status', 'request_priority',
            'has_unread', 'recently_active', 'search'
        ]
    
    def filter_has_unread(self, queryset, name, value):
        """Filter rooms with unread messages for current user"""
        if value and hasattr(self.request, 'user') and self.request.user.is_authenticated:
            user = self.request.user
            rooms_with_unread = []
            
            for room in queryset:
                if room.get_unread_count(user) > 0:
                    rooms_with_unread.append(room.id)
            
            return queryset.filter(id__in=rooms_with_unread)
        return queryset
    
    def filter_recently_active(self, queryset, name, value):
        """Filter recently active rooms (last 24 hours)"""
        if value:
            cutoff = timezone.now() - timedelta(hours=24)
            return queryset.filter(updated_at__gte=cutoff)
        return queryset
    
    def filter_search(self, queryset, name, value):
        """Search in request title and description"""
        if value:
            return queryset.filter(
                models.Q(request__title__icontains=value) |
                models.Q(request__description__icontains=value)
            )
        return queryset
