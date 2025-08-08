import django_filters
from django.db.models import Q
from .models import ServiceRequest, ServiceRequestCategory


class ServiceRequestFilter(django_filters.FilterSet):
    """Service request filters"""
    
    status = django_filters.MultipleChoiceFilter(
        choices=ServiceRequest.STATUS_CHOICES,
        field_name='status',
        lookup_expr='in'
    )
    
    priority = django_filters.MultipleChoiceFilter(
        choices=ServiceRequest.PRIORITY_CHOICES,
        field_name='priority',
        lookup_expr='in'
    )
    
    category = django_filters.ModelMultipleChoiceFilter(
        queryset=ServiceRequestCategory.objects.filter(is_active=True),
        field_name='category'
    )
    
    client = django_filters.UUIDFilter(field_name='client__id')
    accountant = django_filters.UUIDFilter(field_name='accountant__id')
    
    # Date filters
    created_after = django_filters.DateFilter(field_name='created_at', lookup_expr='date__gte')
    created_before = django_filters.DateFilter(field_name='created_at', lookup_expr='date__lte')
    due_after = django_filters.DateFilter(field_name='due_date', lookup_expr='gte')
    due_before = django_filters.DateFilter(field_name='due_date', lookup_expr='lte')
    
    # Special filters
    is_overdue = django_filters.BooleanFilter(method='filter_overdue')
    has_accountant = django_filters.BooleanFilter(method='filter_has_accountant')
    
    # Tag filter
    tags = django_filters.CharFilter(method='filter_tags')
    
    class Meta:
        model = ServiceRequest
        fields = [
            'status', 'priority', 'category', 'client', 'accountant',
            'created_after', 'created_before', 'due_after', 'due_before',
            'is_overdue', 'has_accountant', 'tags'
        ]
    
    def filter_overdue(self, queryset, name, value):
        from django.utils import timezone
        if value:
            return queryset.filter(
                due_date__lt=timezone.now().date(),
                status__in=['new', 'in_progress', 'review']
            )
        return queryset.exclude(
            due_date__lt=timezone.now().date(),
            status__in=['new', 'in_progress', 'review']
        )
    
    def filter_has_accountant(self, queryset, name, value):
        if value:
            return queryset.filter(accountant__isnull=False)
        return queryset.filter(accountant__isnull=True)
    
    def filter_tags(self, queryset, name, value):
        # Filter by tags (case-insensitive partial match)
        return queryset.filter(tags__icontains=value)
