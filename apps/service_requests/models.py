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
        return f"{self.title} - {self.client.full_name}"
    
    def clean(self):
        # Validate accountant role
        if self.accountant and self.accountant.role != 'accountant':
            raise ValidationError("Assigned user must be an accountant.")
        
        # Validate client role
        if self.client.role != 'client':
            raise ValidationError("Request creator must be a client.")
    
    def save(self, *args, **kwargs):
        # Update timestamps based on status changes
        if self.pk:
            old_instance = ServiceRequest.objects.get(pk=self.pk)
            if old_instance.status != self.status:
                if self.status == 'in_progress' and not self.started_at:
                    self.started_at = timezone.now()
                elif self.status == 'completed' and not self.completed_at:
                    self.completed_at = timezone.now()
                elif self.status == 'closed' and not self.closed_at:
                    self.closed_at = timezone.now()
        
        self.clean()
        super().save(*args, **kwargs)
    
    @property
    def is_overdue(self):
        if self.due_date and self.status not in ['completed', 'closed']:
            return timezone.now().date() > self.due_date
        return False
    
    @property
    def duration_days(self):
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
        return f"Assignment: {self.request.title} to {self.to_accountant.full_name}"
    
    def clean(self):
        if self.to_accountant.role != 'accountant':
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
        return f"Note by {self.author.full_name} on {self.request.title}"


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
