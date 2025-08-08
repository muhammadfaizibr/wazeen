from rest_framework import generics, status, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters
from django.shortcuts import get_object_or_404
from django.db.models import Q, Count
from django.utils import timezone

from .models import ServiceRequest, ServiceRequestCategory, RequestNote, RequestAssignment
from .serializers import (
    ServiceRequestListSerializer,
    ServiceRequestDetailSerializer,
    ServiceRequestCreateSerializer,
    ServiceRequestUpdateSerializer,
    ServiceRequestCategorySerializer,
    RequestNoteSerializer,
    ServiceRequestAssignSerializer
)
from .filters import ServiceRequestFilter
from utils.permissions import IsOwnerOrReadOnly


class ServiceRequestCategoryListView(generics.ListAPIView):
    """List all active service request categories"""
    queryset = ServiceRequestCategory.objects.filter(is_active=True)
    serializer_class = ServiceRequestCategorySerializer
    permission_classes = [permissions.IsAuthenticated]


class ServiceRequestListCreateView(generics.ListCreateAPIView):
    """List and create service requests"""
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = ServiceRequestFilter
    search_fields = ['title', 'description', 'client__first_name', 'client__last_name', 'client__email']
    ordering_fields = ['created_at', 'updated_at', 'due_date', 'priority', 'status']
    ordering = ['-created_at']
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        
        if user.role == 'admin':
            return ServiceRequest.objects.all().select_related(
                'client', 'accountant', 'category'
            ).prefetch_related('notes', 'files')
        elif user.role == 'accountant':
            return ServiceRequest.objects.filter(
                Q(accountant=user) | Q(accountant__isnull=True)
            ).select_related('client', 'accountant', 'category').prefetch_related('notes', 'files')
        else:  # client
            return ServiceRequest.objects.filter(client=user).select_related(
                'accountant', 'category'
            ).prefetch_related('notes', 'files')
    
    def get_serializer_class(self):
        if self.request.method == 'POST':
            return ServiceRequestCreateSerializer
        return ServiceRequestListSerializer


class ServiceRequestDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Retrieve, update, and delete service requests"""
    serializer_class = ServiceRequestDetailSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        
        if user.role == 'admin':
            return ServiceRequest.objects.all()
        elif user.role == 'accountant':
            return ServiceRequest.objects.filter(
                Q(accountant=user) | Q(accountant__isnull=True)
            )
        else:  # client
            return ServiceRequest.objects.filter(client=user)
    
    def get_serializer_class(self):
        if self.request.method in ['PUT', 'PATCH']:
            return ServiceRequestUpdateSerializer
        return ServiceRequestDetailSerializer
    
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        
        # Only clients can delete their own requests, and only if not closed
        if request.user.role != 'client' or instance.client != request.user:
            return Response(
                {'error': 'You can only delete your own requests.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        if instance.status == 'closed':
            return Response(
                {'error': 'Cannot delete closed requests.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)


class RequestNoteListCreateView(generics.ListCreateAPIView):
    """List and create request notes"""
    serializer_class = RequestNoteSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        request_id = self.kwargs['request_id']
        user = self.request.user
        
        # Verify user has access to this request
        request_obj = get_object_or_404(ServiceRequest, id=request_id)
        
        if user.role == 'admin':
            pass  # Admin can see all
        elif user.role == 'accountant':
            if request_obj.accountant != user:
                return RequestNote.objects.none()
        else:  # client
            if request_obj.client != user:
                return RequestNote.objects.none()
        
        # Filter notes based on user role
        if user.role in ['admin', 'accountant']:
            return RequestNote.objects.filter(request_id=request_id).select_related('author')
        else:
            return RequestNote.objects.filter(
                request_id=request_id, is_internal=False
            ).select_related('author')
    
    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['request_obj'] = get_object_or_404(ServiceRequest, id=self.kwargs['request_id'])
        return context


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def assign_request(request, request_id):
    """Assign request to an accountant"""
    service_request = get_object_or_404(ServiceRequest, id=request_id)
    
    # Only admins and the current accountant can reassign
    if request.user.role not in ['admin'] and service_request.accountant != request.user:
        return Response(
            {'error': 'Permission denied.'},
            status=status.HTTP_403_FORBIDDEN
        )
    
    serializer = ServiceRequestAssignSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    
    accountant = serializer.validated_data['accountant_id']
    reason = serializer.validated_data.get('reason', '')
    
    # Create assignment record
    RequestAssignment.objects.create(
        request=service_request,
        from_accountant=service_request.accountant,
        to_accountant=accountant,
        assigned_by=request.user,
        reason=reason
    )
    
    # Update request
    service_request.accountant = accountant
    service_request.save()
    
    return Response({
        'detail': f'Request assigned to {accountant.full_name}.',
        'request': ServiceRequestDetailSerializer(
            service_request, context={'request': request}
        ).data
    })


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def update_status(request, request_id):
    """Update request status"""
    service_request = get_object_or_404(ServiceRequest, id=request_id)
    
    # Check permissions
    user = request.user
    if user.role == 'client' and service_request.client != user:
        return Response(
            {'error': 'Permission denied.'},
            status=status.HTTP_403_FORBIDDEN
        )
    elif user.role == 'accountant' and service_request.accountant != user:
        return Response(
            {'error': 'Permission denied.'},
            status=status.HTTP_403_FORBIDDEN
        )
    
    new_status = request.data.get('status')
    reason = request.data.get('reason', '')
    
    if not new_status:
        return Response(
            {'error': 'Status is required.'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Validate status transition
    if new_status not in dict(ServiceRequest.STATUS_CHOICES):
        return Response(
            {'error': 'Invalid status.'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Clients can only approve completed requests
    if user.role == 'client':
        if service_request.status == 'completed' and new_status == 'closed':
            pass  # Valid transition
        elif service_request.status != new_status:
            return Response(
                {'error': 'Clients can only approve completed requests.'},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    # Cannot reopen closed requests
    if service_request.status == 'closed':
        return Response(
            {'error': 'Cannot reopen closed requests.'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Update status
    old_status = service_request.status
    service_request.status = new_status
    service_request.save()
    
    # Create status history record
    from .models import RequestStatusHistory
    RequestStatusHistory.objects.create(
        request=service_request,
        from_status=old_status,
        to_status=new_status,
        changed_by=user,
        reason=reason
    )
    
    return Response({
        'detail': f'Status updated from {old_status} to {new_status}.',
        'request': ServiceRequestDetailSerializer(
            service_request, context={'request': request}
        ).data
    })


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def dashboard_stats(request):
    """Get dashboard statistics for the current user"""
    user = request.user
    
    if user.role == 'admin':
        queryset = ServiceRequest.objects.all()
    elif user.role == 'accountant':
        queryset = ServiceRequest.objects.filter(accountant=user)
    else:  # client
        queryset = ServiceRequest.objects.filter(client=user)
    
    # Get status counts
    status_counts = queryset.values('status').annotate(count=Count('id'))
    status_stats = {item['status']: item['count'] for item in status_counts}
    
    # Get priority counts
    priority_counts = queryset.values('priority').annotate(count=Count('id'))
    priority_stats = {item['priority']: item['count'] for item in priority_counts}
    
    # Get overdue requests
    overdue_count = queryset.filter(
        due_date__lt=timezone.now().date(),
        status__in=['new', 'in_progress', 'review']
    ).count()
    
    # Recent requests
    recent_requests = ServiceRequestListSerializer(
        queryset.order_by('-created_at')[:5],
        many=True,
        context={'request': request}
    ).data
    
    return Response({
        'status_stats': status_stats,
        'priority_stats': priority_stats,
        'overdue_count': overdue_count,
        'recent_requests': recent_requests,
        'total_requests': queryset.count()
    })

