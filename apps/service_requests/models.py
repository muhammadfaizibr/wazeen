import uuid
from django.db import models
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

User = get_user_model()


class ServiceRequestCategory(models.Model):
    """Service request categories"""
    name = models.CharField(max_length=100)
    name_ar = models.CharField(max_length=100, blank=True)
    description = models.TextField(blank=True)
    description_ar = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'service_request_categories'
        verbose_name_plural = 'Service Request Categories'
    
    def __str__(self):
        return self.name


class ServiceRequest(models.Model):
    """Main service request model"""
    
    STATUS_CHOICES = [
        ('new', 'New'),
        ('in_progress', 'In Progress'),
        ('review', 'Under Review'),
        ('completed', 'Completed'),
        ('closed', 'Closed'),
    ]
    
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    client = models.ForeignKey(User, on_delete=models.CASCADE, related_name='client_requests')
    accountant = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_requests')
    
    # Request Details
    title = models.CharField(max_length=200)
    description = models.TextField()
    category = models.ForeignKey(ServiceRequestCategory, on_delete=models.SET_NULL, null=True, blank=True)
    
    # Status and Priority
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='new')
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='medium')
    
    # Dates
    due_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    
    # Time tracking
    estimated_hours = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    actual_hours = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    
    # Additional fields
    tags = models.JSONField(default=list, blank=True)
    custom_fields = models.JSONField(default=dict, blank=True)
    
    class Meta:
        db_table = 'service_requests'
        indexes = [
            models.Index(fields=['client']),
            models.Index(fields=['accountant']),
            models.Index(fields=['status']),
            models.Index(fields=['priority']),
            models.Index(fields=['created_at']),
            models.Index(fields=['due_date']),
        ]
        ordering = ['-created_at']
    
    def __str__(self):
        client_name = self.client.full_name if self.client and hasattr(self.client, 'full_name') else 'Unknown Client'
        return f"{self.title} - {client_name}"
        
        # Add these methods to your ServiceRequest model class

    def can_user_view_files(self, user):
        """Check if user can view files for this service request"""
        # Client can view their own request files
        if self.client == user:
            return True
        
        # Assigned accountant can view files
        if self.accountant == user:
            return True
        
        # Add any other business logic here (e.g., managers, admins)
        # Example: if user has admin role
        if hasattr(user, 'role') and user.role == 'admin':
            return True
        
        return False

    def can_user_manage_files(self, user):
        """Check if user can manage (upload, delete, etc.) files for this service request"""
        # Client can manage files for their own request
        if self.client == user:
            return True
        
        # Assigned accountant can manage files
        if self.accountant == user:
            return True
        
        # Add any other business logic here (e.g., managers, admins)
        # Example: if user has admin role
        if hasattr(user, 'role') and user.role == 'admin':
            return True
        
        return False

    def can_user_upload_files(self, user):
        """Check if user can upload files for this service request"""
        # Client can upload files for their own request
        if self.client == user:
            return True
        
        # Assigned accountant can upload files
        if self.accountant == user:
            return True
        
        # Add any other business logic here (e.g., managers, admins)
        # Example: if user has admin role
        if hasattr(user, 'role') and user.role == 'admin':
            return True
        
        # Optional: Restrict uploads based on request status
        # Example: Don't allow uploads if request is closed
        # if self.status == 'closed':
        #     return False
        
        return False

    def can_user_download_files(self, user):
        """Check if user can download files for this service request"""
        # Client can download files for their own request
        if self.client == user:
            return True
        
        # Assigned accountant can download files
        if self.accountant == user:
            return True
        
        # Add any other business logic here (e.g., managers, admins)
        # Example: if user has admin role
        if hasattr(user, 'role') and user.role == 'admin':
            return True
        
        return False

    def can_user_share_files(self, user):
        """Check if user can share files for this service request"""
        # Client can share files for their own request
        if self.client == user:
            return True
        
        # Assigned accountant can share files
        if self.accountant == user:
            return True
        
        # Add any other business logic here (e.g., managers, admins)
        # Example: if user has admin role
        if hasattr(user, 'role') and user.role == 'admin':
            return True
        
        return False
    
    def clean(self):
        """Validate model fields"""
        errors = {}
        
        # Validate accountant role (only if accountant is assigned and has role attribute)
        if self.accountant and hasattr(self.accountant, 'role') and self.accountant.role != 'accountant':
            errors['accountant'] = "Assigned user must be an accountant."
        
        # Validate client role (only if client exists and has role attribute)
        if self.client and hasattr(self.client, 'role') and self.client.role != 'client':
            errors['client'] = "Request creator must be a client."
        
        if errors:
            raise ValidationError(errors)
    
    def save(self, *args, **kwargs):
        """Custom save method with status change handling"""
        is_new = self.pk is None
        old_status = None
        skip_validation = kwargs.pop('skip_validation', False)
        
        # Get old status if this is an update
        if not is_new:
            try:
                old_instance = ServiceRequest.objects.get(pk=self.pk)
                old_status = old_instance.status
            except ServiceRequest.DoesNotExist:
                # Handle case where object was deleted between operations
                is_new = True
        
        # Update timestamps based on status changes
        if not is_new and old_status and old_status != self.status:
            if self.status == 'in_progress' and not self.started_at:
                self.started_at = timezone.now()
            elif self.status == 'completed' and not self.completed_at:
                self.completed_at = timezone.now()
            elif self.status == 'closed' and not self.closed_at:
                self.closed_at = timezone.now()
        
        # Only run clean validation if not skipped and not a new object during creation
        if not skip_validation:
            try:
                self.clean()
            except ValidationError as e:
                # During creation, log the error but don't prevent saving
                # This allows DRF serializers to handle validation
                if not is_new:
                    raise e
        
        super().save(*args, **kwargs)
    
    @property
    def is_overdue(self):
        """Check if the service request is overdue"""
        if self.due_date and self.status not in ['completed', 'closed']:
            return timezone.now().date() > self.due_date
        return False
    
    @property
    def duration_days(self):
        """Calculate duration in days"""
        if self.closed_at:
            return (self.closed_at - self.created_at).days
        return (timezone.now() - self.created_at).days


class RequestAssignment(models.Model):
    """Track request assignment history"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    request = models.ForeignKey(ServiceRequest, on_delete=models.CASCADE, related_name='assignments')
    from_accountant = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='assignments_from')
    to_accountant = models.ForeignKey(User, on_delete=models.CASCADE, related_name='assignments_to')
    assigned_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='assignments_made')
    reason = models.TextField(blank=True)
    assigned_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'request_assignments'
        ordering = ['-assigned_at']
    
    def __str__(self):
        to_name = self.to_accountant.full_name if hasattr(self.to_accountant, 'full_name') else self.to_accountant.email
        return f"Assignment: {self.request.title} to {to_name}"
    
    def clean(self):
        if self.to_accountant and hasattr(self.to_accountant, 'role') and self.to_accountant.role != 'accountant':
            raise ValidationError("Can only assign to accountants.")


class RequestNote(models.Model):
    """Internal notes for requests"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    request = models.ForeignKey(ServiceRequest, on_delete=models.CASCADE, related_name='notes')
    author = models.ForeignKey(User, on_delete=models.CASCADE)
    content = models.TextField()
    is_internal = models.BooleanField(default=False, help_text="Internal notes are only visible to accountants and admins")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'request_notes'
        ordering = ['-created_at']
    
    def __str__(self):
        author_name = self.author.full_name if hasattr(self.author, 'full_name') else self.author.email
        return f"Note by {author_name} on {self.request.title}"


class RequestStatusHistory(models.Model):
    """Track status changes"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    request = models.ForeignKey(ServiceRequest, on_delete=models.CASCADE, related_name='status_history')
    from_status = models.CharField(max_length=20, blank=True)
    to_status = models.CharField(max_length=20)
    changed_by = models.ForeignKey(User, on_delete=models.CASCADE)
    reason = models.TextField(blank=True)
    changed_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'request_status_history'
        ordering = ['-changed_at']
    
    def __str__(self):
        return f"{self.request.title}: {self.from_status} → {self.to_status}"