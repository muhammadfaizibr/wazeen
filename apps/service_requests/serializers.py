from rest_framework import serializers
from django.utils import timezone
from django.core.exceptions import ValidationError as DjangoValidationError
from apps.authentication.serializers import UserSerializer
from .models import ServiceRequest, ServiceRequestCategory, RequestNote, RequestAssignment


class ServiceRequestCategorySerializer(serializers.ModelSerializer):
    """Service request category serializer"""
    
    class Meta:
        model = ServiceRequestCategory
        fields = ['id', 'name', 'name_ar', 'description', 'description_ar', 'is_active']


class RequestNoteSerializer(serializers.ModelSerializer):
    """Request note serializer"""
    author = UserSerializer(read_only=True)
    author_name = serializers.SerializerMethodField()
    
    class Meta:
        model = RequestNote
        fields = ['id', 'content', 'is_internal', 'author', 'author_name', 'created_at', 'updated_at']
        read_only_fields = ['id', 'author', 'created_at', 'updated_at']
    
    def get_author_name(self, obj):
        """Get author name safely"""
        if obj.author:
            return getattr(obj.author, 'full_name', obj.author.email)
        return None
    
    def create(self, validated_data):
        validated_data['author'] = self.context['request'].user
        validated_data['request'] = self.context['request_obj']
        return super().create(validated_data)


class RequestAssignmentSerializer(serializers.ModelSerializer):
    """Request assignment serializer"""
    from_accountant = UserSerializer(read_only=True)
    to_accountant = UserSerializer(read_only=True)
    assigned_by = UserSerializer(read_only=True)
    
    class Meta:
        model = RequestAssignment
        fields = [
            'id', 'from_accountant', 'to_accountant', 'assigned_by',
            'reason', 'assigned_at'
        ]
        read_only_fields = ['id', 'assigned_at']


class ServiceRequestCreateSerializer(serializers.ModelSerializer):
    """Service request creation serializer"""
    
    category = serializers.PrimaryKeyRelatedField(
        queryset=ServiceRequestCategory.objects.filter(is_active=True),
        required=False,
        allow_null=True,
        help_text="Optional category for the service request"
    )

    class Meta:
        model = ServiceRequest
        fields = [
            'title', 'description', 'category', 'priority', 'due_date',
            'estimated_hours', 'tags', 'custom_fields'
        ]
        extra_kwargs = {
            'title': {
                'required': True, 
                'allow_blank': False,
                'help_text': 'Title of the service request'
            },
            'description': {
                'required': True, 
                'allow_blank': False,
                'help_text': 'Detailed description of the service request'
            },
            'priority': {
                'required': False,
                'help_text': 'Priority level (low, medium, high, urgent)'
            },
            'due_date': {
                'required': False,
                'help_text': 'Due date in YYYY-MM-DD format'
            },
            'estimated_hours': {
                'required': False,
                'help_text': 'Estimated hours to complete the request'
            },
            'tags': {
                'required': False,
                'help_text': 'List of tags for categorization'
            },
            'custom_fields': {
                'required': False,
                'help_text': 'Additional custom fields as JSON'
            },
        }

    def validate_title(self, value):
        """Validate title field"""
        if not value or not value.strip():
            raise serializers.ValidationError("Title cannot be empty.")
        return value.strip()

    def validate_description(self, value):
        """Validate description field"""
        if not value or not value.strip():
            raise serializers.ValidationError("Description cannot be empty.")
        return value.strip()

    def validate_priority(self, value):
        """Validate priority field"""
        if value and value not in dict(ServiceRequest.PRIORITY_CHOICES):
            valid_choices = ', '.join(dict(ServiceRequest.PRIORITY_CHOICES).keys())
            raise serializers.ValidationError(f"Invalid priority. Choose from: {valid_choices}")
        return value

    def validate_estimated_hours(self, value):
        """Validate estimated hours"""
        if value is not None and value < 0:
            raise serializers.ValidationError("Estimated hours cannot be negative.")
        if value is not None and value > 1000:
            raise serializers.ValidationError("Estimated hours cannot exceed 1000.")
        return value

    def validate_due_date(self, value):
        """Validate due date"""
        if value and value < timezone.now().date():
            raise serializers.ValidationError("Due date cannot be in the past.")
        return value

    def validate(self, attrs):
        """Validate the entire object"""
        user = self.context.get('request', {}).user
        
        # Check user role
        if not user or not hasattr(user, 'role') or user.role != 'client':
            raise serializers.ValidationError({
                "user": "Only clients can create service requests."
            })
        
        return attrs

    def create(self, validated_data):
        """Create service request with proper error handling"""
        try:
            # The client will be set in the view's perform_create method
            return super().create(validated_data)
        except DjangoValidationError as e:
            # Convert Django ValidationError to DRF ValidationError
            if hasattr(e, 'message_dict'):
                raise serializers.ValidationError(e.message_dict)
            else:
                raise serializers.ValidationError(str(e))
        except Exception as e:
            raise serializers.ValidationError(f"Error creating service request: {str(e)}")


class ServiceRequestListSerializer(serializers.ModelSerializer):
    """Service request list serializer (minimal fields for list view)"""
    client_name = serializers.SerializerMethodField()
    accountant_name = serializers.SerializerMethodField()
    category_name = serializers.CharField(source='category.name', read_only=True)
    is_overdue = serializers.ReadOnlyField()
    duration_days = serializers.ReadOnlyField()
    notes_count = serializers.SerializerMethodField()
    files_count = serializers.SerializerMethodField()
    
    class Meta:
        model = ServiceRequest
        fields = [
            'id', 'title', 'status', 'priority', 'client_name', 'accountant_name',
            'category_name', 'due_date', 'created_at', 'updated_at', 'is_overdue',
            'duration_days', 'notes_count', 'files_count'
        ]
    
    def get_client_name(self, obj):
        """Get client name safely"""
        if obj.client:
            return getattr(obj.client, 'full_name', obj.client.email)
        return None
    
    def get_accountant_name(self, obj):
        """Get accountant name safely"""
        if obj.accountant:
            return getattr(obj.accountant, 'full_name', obj.accountant.email)
        return None
    
    def get_notes_count(self, obj):
        """Get notes count based on user role"""
        user = self.context.get('request', {}).user if self.context.get('request') else None
        
        if not user:
            return 0
            
        if getattr(user, 'role', None) in ['admin', 'accountant']:
            return obj.notes.count() if hasattr(obj, 'notes') else 0
        return obj.notes.filter(is_internal=False).count() if hasattr(obj, 'notes') else 0
    
    def get_files_count(self, obj):
        """Get files count"""
        if hasattr(obj, 'files'):
            return obj.files.filter(is_deleted=False).count()
        return 0


class ServiceRequestDetailSerializer(serializers.ModelSerializer):
    """Service request detail serializer"""
    client = UserSerializer(read_only=True)
    accountant = UserSerializer(read_only=True)
    category = ServiceRequestCategorySerializer(read_only=True)
    notes = serializers.SerializerMethodField()
    assignments = RequestAssignmentSerializer(many=True, read_only=True)
    is_overdue = serializers.ReadOnlyField()
    duration_days = serializers.ReadOnlyField()
    
    class Meta:
        model = ServiceRequest
        fields = [
            'id', 'title', 'description', 'status', 'priority', 'client',
            'accountant', 'category', 'due_date', 'estimated_hours', 'actual_hours',
            'tags', 'custom_fields', 'created_at', 'updated_at', 'started_at',
            'completed_at', 'closed_at', 'is_overdue', 'duration_days',
            'notes', 'assignments'
        ]
        read_only_fields = [
            'id', 'client', 'created_at', 'updated_at', 'started_at',
            'completed_at', 'closed_at'
        ]
    
    def get_notes(self, obj):
        """Get notes based on user permissions"""
        user = self.context.get('request', {}).user if self.context.get('request') else None
        
        if not user:
            return []
            
        if getattr(user, 'role', None) in ['admin', 'accountant']:
            notes = obj.notes.all() if hasattr(obj, 'notes') else []
        else:
            notes = obj.notes.filter(is_internal=False) if hasattr(obj, 'notes') else []
        
        return RequestNoteSerializer(notes, many=True, context=self.context).data


class ServiceRequestUpdateSerializer(serializers.ModelSerializer):
    """Service request update serializer"""
    
    class Meta:
        model = ServiceRequest
        fields = [
            'title', 'description', 'status', 'priority', 'accountant',
            'due_date', 'estimated_hours', 'actual_hours', 'tags', 'custom_fields'
        ]
    
    def validate_status(self, value):
        """Validate status transitions"""
        user = self.context.get('request', {}).user
        current_status = self.instance.status if self.instance else None
        
        if not user:
            raise serializers.ValidationError("User authentication required.")
        
        # Clients can only change status from 'completed' to 'closed' (approval)
        if getattr(user, 'role', None) == 'client':
            if current_status == 'completed' and value == 'closed':
                return value
            elif current_status != value:
                raise serializers.ValidationError("Clients can only approve completed requests.")
        
        # Cannot reopen closed requests
        if current_status == 'closed':
            raise serializers.ValidationError("Cannot reopen closed requests.")
        
        return value
    
    def validate_accountant(self, value):
        """Validate accountant assignment"""
        if value and hasattr(value, 'role') and value.role != 'accountant':
            raise serializers.ValidationError("Can only assign to accountants.")
        return value
    
    def update(self, instance, validated_data):
        """Update with assignment tracking"""
        user = self.context.get('request', {}).user
        
        # Track accountant assignment
        if 'accountant' in validated_data and validated_data['accountant'] != instance.accountant:
            try:
                RequestAssignment.objects.create(
                    request=instance,
                    from_accountant=instance.accountant,
                    to_accountant=validated_data['accountant'],
                    assigned_by=user,
                    reason="Reassigned via API"
                )
            except Exception as e:
                # Log the error but don't prevent the update
                pass
        
        return super().update(instance, validated_data)


class ServiceRequestAssignSerializer(serializers.Serializer):
    """Service request assignment serializer"""
    accountant_id = serializers.UUIDField(required=True)
    reason = serializers.CharField(max_length=500, required=False, allow_blank=True)
    
    def validate_accountant_id(self, value):
        """Validate accountant ID"""
        from apps.authentication.models import User
        try:
            accountant = User.objects.get(id=value, role='accountant', is_active=True)
            return accountant
        except User.DoesNotExist:
            raise serializers.ValidationError("Invalid accountant ID or accountant is not active.")