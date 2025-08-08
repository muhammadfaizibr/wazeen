import django_filters
from django.db.models import Q
from .models import File, FileCategory


class FileFilter(django_filters.FilterSet):
    """File filtering"""
    
    category = django_filters.ModelChoiceFilter(
        queryset=FileCategory.objects.filter(is_active=True)
    )
    file_type = django_filters.ChoiceFilter(
        choices=[
            ('image', 'Images'),
            ('document', 'Documents'),
            ('other', 'Other')
        ],
        method='filter_by_type'
    )
    search = django_filters.CharFilter(method='filter_search')
    uploaded_by = django_filters.CharFilter(
        field_name='uploaded_by__email',
        lookup_expr='icontains'
    )
    date_from = django_filters.DateFilter(
        field_name='created_at',
        lookup_expr='gte'
    )
    date_to = django_filters.DateFilter(
        field_name='created_at',
        lookup_expr='lte'
    )
    
    class Meta:
        model = File
        fields = ['category', 'file_type', 'search', 'uploaded_by', 'date_from', 'date_to']
    
    def filter_by_type(self, queryset, name, value):
        if value == 'image':
            return queryset.filter(mime_type__startswith='image/')
        elif value == 'document':
            return queryset.filter(
                Q(mime_type__contains='pdf') |
                Q(mime_type__contains='document') |
                Q(mime_type__contains='text/') |
                Q(mime_type__contains='spreadsheet') |
                Q(mime_type__contains='presentation')
            )
        elif value == 'other':
            return queryset.exclude(
                Q(mime_type__startswith='image/') |
                Q(mime_type__contains='pdf') |
                Q(mime_type__contains='document') |
                Q(mime_type__contains='text/') |
                Q(mime_type__contains='spreadsheet') |
                Q(mime_type__contains='presentation')
            )
        return queryset
    
    def filter_search(self, queryset, name, value):
        return queryset.filter(
            Q(original_filename__icontains=value) |
            Q(tags__icontains=value) |
            Q(metadata__icontains=value)
        )

