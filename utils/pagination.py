from rest_framework.pagination import PageNumberPagination, LimitOffsetPagination, CursorPagination
from rest_framework.response import Response
from django.conf import settings
from collections import OrderedDict
import math


class CustomPagination(PageNumberPagination):
    """
    Custom pagination class - main pagination for the project
    """
    page_size = getattr(settings, 'DEFAULT_PAGE_SIZE', 20)
    page_size_query_param = 'page_size'
    max_page_size = getattr(settings, 'MAX_PAGE_SIZE', 100)
    page_query_param = 'page'
    
    def get_paginated_response(self, data):
        return Response(OrderedDict([
            ('success', True),
            ('count', self.page.paginator.count),
            ('total_pages', self.page.paginator.num_pages),
            ('current_page', self.page.number),
            ('page_size', self.get_page_size(self.request)),
            ('next', self.get_next_link()),
            ('previous', self.get_previous_link()),
            ('results', data)
        ]))
    
    def get_paginated_response_schema(self, schema):
        return {
            'type': 'object',
            'properties': {
                'success': {
                    'type': 'boolean',
                    'example': True,
                },
                'count': {
                    'type': 'integer',
                    'example': 123,
                },
                'total_pages': {
                    'type': 'integer',
                    'example': 7,
                },
                'current_page': {
                    'type': 'integer',
                    'example': 1,
                },
                'page_size': {
                    'type': 'integer',
                    'example': 20,
                },
                'next': {
                    'type': 'string',
                    'nullable': True,
                    'format': 'uri',
                    'example': 'http://api.example.org/accounts/?page=4'
                },
                'previous': {
                    'type': 'string',
                    'nullable': True,
                    'format': 'uri',
                    'example': 'http://api.example.org/accounts/?page=2'
                },
                'results': schema,
            },
        }


class StandardResultsSetPagination(CustomPagination):
    """
    Standard pagination class with page numbers (alias for CustomPagination)
    """
    pass


class LargeResultsSetPagination(PageNumberPagination):
    """
    Pagination for large datasets with bigger default page size
    """
    page_size = getattr(settings, 'LARGE_PAGE_SIZE', 50)
    page_size_query_param = 'page_size'
    max_page_size = getattr(settings, 'MAX_LARGE_PAGE_SIZE', 200)
    page_query_param = 'page'
    
    def get_paginated_response(self, data):
        return Response(OrderedDict([
            ('success', True),
            ('count', self.page.paginator.count),
            ('total_pages', self.page.paginator.num_pages),
            ('current_page', self.page.number),
            ('page_size', self.get_page_size(self.request)),
            ('next', self.get_next_link()),
            ('previous', self.get_previous_link()),
            ('results', data)
        ]))


class SmallResultsSetPagination(PageNumberPagination):
    """
    Pagination for small datasets with smaller default page size
    """
    page_size = getattr(settings, 'SMALL_PAGE_SIZE', 10)
    page_size_query_param = 'page_size'
    max_page_size = getattr(settings, 'MAX_SMALL_PAGE_SIZE', 50)
    page_query_param = 'page'
    
    def get_paginated_response(self, data):
        return Response(OrderedDict([
            ('success', True),
            ('count', self.page.paginator.count),
            ('total_pages', self.page.paginator.num_pages),
            ('current_page', self.page.number),
            ('page_size', self.get_page_size(self.request)),
            ('next', self.get_next_link()),
            ('previous', self.get_previous_link()),
            ('results', data)
        ]))


class CustomLimitOffsetPagination(LimitOffsetPagination):
    """
    Custom limit/offset pagination with enhanced response format
    """
    default_limit = getattr(settings, 'DEFAULT_PAGE_SIZE', 20)
    limit_query_param = 'limit'
    offset_query_param = 'offset'
    max_limit = getattr(settings, 'MAX_PAGE_SIZE', 100)
    
    def get_paginated_response(self, data):
        return Response(OrderedDict([
            ('success', True),
            ('count', self.count),
            ('limit', self.limit),
            ('offset', self.offset),
            ('next', self.get_next_link()),
            ('previous', self.get_previous_link()),
            ('results', data)
        ]))
    
    def get_paginated_response_schema(self, schema):
        return {
            'type': 'object',
            'properties': {
                'success': {
                    'type': 'boolean',
                    'example': True,
                },
                'count': {
                    'type': 'integer',
                    'example': 123,
                },
                'limit': {
                    'type': 'integer',
                    'example': 20,
                },
                'offset': {
                    'type': 'integer',
                    'example': 0,
                },
                'next': {
                    'type': 'string',
                    'nullable': True,
                    'format': 'uri',
                    'example': 'http://api.example.org/accounts/?limit=20&offset=20'
                },
                'previous': {
                    'type': 'string',
                    'nullable': True,
                    'format': 'uri',
                    'example': 'http://api.example.org/accounts/?limit=20&offset=0'
                },
                'results': schema,
            },
        }


class CustomCursorPagination(CursorPagination):
    """
    Custom cursor pagination for time-series data
    """
    page_size = getattr(settings, 'DEFAULT_PAGE_SIZE', 20)
    page_size_query_param = 'page_size'
    max_page_size = getattr(settings, 'MAX_PAGE_SIZE', 100)
    ordering = '-created_at'  # Default ordering field
    cursor_query_param = 'cursor'
    
    def get_paginated_response(self, data):
        return Response(OrderedDict([
            ('success', True),
            ('next', self.get_next_link()),
            ('previous', self.get_previous_link()),
            ('results', data)
        ]))


class DashboardPagination(PageNumberPagination):
    """
    Special pagination for dashboard views with minimal page size
    """
    page_size = 5
    page_size_query_param = 'page_size'
    max_page_size = 20
    page_query_param = 'page'
    
    def get_paginated_response(self, data):
        return Response(OrderedDict([
            ('success', True),
            ('count', self.page.paginator.count),
            ('current_page', self.page.number),
            ('total_pages', self.page.paginator.num_pages),
            ('has_more', self.page.has_next()),
            ('results', data)
        ]))


class NoPagination:
    """
    Disable pagination - return all results
    Use with caution on large datasets
    """
    def paginate_queryset(self, queryset, request, view=None):
        return None
    
    def get_paginated_response(self, data):
        return Response(OrderedDict([
            ('success', True),
            ('count', len(data)),
            ('results', data)
        ]))


class MetaPagination(PageNumberPagination):
    """
    Pagination with additional metadata
    """
    page_size = getattr(settings, 'DEFAULT_PAGE_SIZE', 20)
    page_size_query_param = 'page_size'
    max_page_size = getattr(settings, 'MAX_PAGE_SIZE', 100)
    page_query_param = 'page'
    
    def get_paginated_response(self, data):
        return Response(OrderedDict([
            ('success', True),
            ('data', data),
            ('meta', {
                'pagination': {
                    'count': self.page.paginator.count,
                    'page': self.page.number,
                    'pages': self.page.paginator.num_pages,
                    'page_size': self.get_page_size(self.request),
                    'has_next': self.page.has_next(),
                    'has_previous': self.page.has_previous(),
                }
            }),
            ('links', {
                'next': self.get_next_link(),
                'previous': self.get_previous_link(),
                'first': self.get_first_link(),
                'last': self.get_last_link(),
            })
        ]))
    
    def get_first_link(self):
        if not self.page.has_previous():
            return None
        url = self.request.build_absolute_uri()
        return self.replace_query_param(url, self.page_query_param, 1)
    
    def get_last_link(self):
        if not self.page.has_next():
            return None
        url = self.request.build_absolute_uri()
        return self.replace_query_param(url, self.page_query_param, self.page.paginator.num_pages)


def paginate_queryset(queryset, request, page_size=None, pagination_class=None):
    """
    Utility function to manually paginate a queryset
    
    Args:
        queryset: Django queryset to paginate
        request: HTTP request object
        page_size: Optional page size override
        pagination_class: Optional pagination class to use
    
    Returns:
        Tuple of (paginated_data, pagination_info)
    """
    if pagination_class is None:
        pagination_class = StandardResultsSetPagination
    
    paginator = pagination_class()
    
    if page_size:
        paginator.page_size = page_size
    
    page = paginator.paginate_queryset(queryset, request)
    
    if page is not None:
        pagination_info = {
            'count': paginator.page.paginator.count,
            'total_pages': paginator.page.paginator.num_pages,
            'current_page': paginator.page.number,
            'page_size': paginator.get_page_size(request),
            'has_next': paginator.page.has_next(),
            'has_previous': paginator.page.has_previous(),
            'next_url': paginator.get_next_link(),
            'previous_url': paginator.get_previous_link(),
        }
        return page, pagination_info
    
    return queryset, None


def get_pagination_params(request):
    """
    Extract pagination parameters from request
    
    Args:
        request: HTTP request object
    
    Returns:
        Dictionary with pagination parameters
    """
    return {
        'page': request.query_params.get('page', 1),
        'page_size': request.query_params.get('page_size', getattr(settings, 'DEFAULT_PAGE_SIZE', 20)),
        'limit': request.query_params.get('limit'),
        'offset': request.query_params.get('offset', 0),
        'cursor': request.query_params.get('cursor'),
    }


class PaginationMixin:
    """
    Mixin to add pagination utilities to views
    """
    
    def get_pagination_context(self):
        """Get pagination context for templates"""
        page_obj = getattr(self, 'page_obj', None)
        if not page_obj:
            return {}
        
        return {
            'is_paginated': page_obj.paginator.count > page_obj.paginator.per_page,
            'page_obj': page_obj,
            'paginator': page_obj.paginator,
            'page_range': self.get_page_range(page_obj),
        }
    
    def get_page_range(self, page_obj, window=5):
        """Get a range of page numbers around current page"""
        current_page = page_obj.number
        total_pages = page_obj.paginator.num_pages
        
        start = max(1, current_page - window // 2)
        end = min(total_pages + 1, start + window)
        
        # Adjust start if we're near the end
        if end - start < window:
            start = max(1, end - window)
        
        return range(start, end)


# Predefined pagination configurations
PAGINATION_CONFIGS = {
    'standard': StandardResultsSetPagination,
    'custom': CustomPagination,
    'large': LargeResultsSetPagination,
    'small': SmallResultsSetPagination,
    'dashboard': DashboardPagination,
    'cursor': CustomCursorPagination,
    'offset': CustomLimitOffsetPagination,
    'meta': MetaPagination,
    'none': NoPagination,
}


def get_pagination_class(config_name='custom'):
    """
    Get pagination class by configuration name
    
    Args:
        config_name: Name of pagination configuration
    
    Returns:
        Pagination class
    """
    return PAGINATION_CONFIGS.get(config_name, CustomPagination)