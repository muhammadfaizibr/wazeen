from rest_framework import serializers
from django.utils import timezone
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
    author_name = serializers.CharField(source='author.full_name', read_only=True)
    
    class Meta:
        model = RequestNote
        fields = ['id', 'content', 'is_internal', 'author', 'author_name', 'created_at', 'updated_at']
        read_only_fields = ['id', 'author', 'created_at', 'updated_at']
    
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


class ServiceRequestListSerializer(serializers.ModelSerializer):
    """Service request list serializer (minimal fields)"""
    client_name = serializers.CharField(source='client.full_name', read_only=True)
    accountant_name = serializers.CharField(source='accountant.full_name', read_only=True)
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
    
    def get_notes_count(self, obj):
        user = self.context.get('request').user
        if user.role in ['admin', 'accountant']:
            return obj.notes.count()
        return obj.notes.filter(is_internal=False).count()
    
    def get_files_count(self, obj):
        return obj.files.filter(is_deleted=False).count()


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
        user = self.context.get('request').user
        if user.role in ['admin', 'accountant']:
            notes = obj.notes.all()
        else:
            notes = obj.notes.filter(is_internal=False)
        
        return RequestNoteSerializer(notes, many=True, context=self.context).data


class ServiceRequestCreateSerializer(serializers.ModelSerializer):
    """Service request creation serializer"""
    
    class Meta:
        model = ServiceRequest
        fields = [
            'title', 'description', 'category', 'priority', 'due_date',
            'estimated_hours', 'tags', 'custom_fields'
        ]
        extra_kwargs = {
            'title': {'required': True},
            'description': {'required': True},
        }
    
    def create(self, validated_data):
        validated_data['client'] = self.context['request'].user
        return super().create(validated_data)
    
    def validate(self, attrs):
        user = self.context['request'].user
        if user.role != 'client':
            raise serializers.ValidationError("Only clients can create service requests.")
        return attrs


class ServiceRequestUpdateSerializer(serializers.ModelSerializer):
    """Service request update serializer"""
    
    class Meta:
        model = ServiceRequest
        fields = [
            'title', 'description', 'status', 'priority', 'accountant',
            'due_date', 'estimated_hours', 'actual_hours', 'tags', 'custom_fields'
        ]
    
    def validate_status(self, value):
        user = self.context['request'].user
        current_status = self.instance.status if self.instance else None
        
        # Clients can only change status from 'completed' to 'closed' (approval)
        if user.role == 'client':
            if current_status == 'completed' and value == 'closed':
                return value
            elif current_status != value:
                raise serializers.ValidationError("Clients can only approve completed requests.")
        
        # Cannot reopen closed requests
        if current_status == 'closed':
            raise serializers.ValidationError("Cannot reopen closed requests.")
        
        return value
    
    def validate_accountant(self, value):
        if value and value.role != 'accountant':
            raise serializers.ValidationError("Can only assign to accountants.")
        return value
    
    def update(self, instance, validated_data):
        user = self.context['request'].user
        
        # Track accountant assignment
        if 'accountant' in validated_data and validated_data['accountant'] != instance.accountant:
            RequestAssignment.objects.create(
                request=instance,
                from_accountant=instance.accountant,
                to_accountant=validated_data['accountant'],
                assigned_by=user,
                reason="Reassigned via API"
            )
        
        return super().update(instance, validated_data)


class ServiceRequestAssignSerializer(serializers.Serializer):
    """Service request assignment serializer"""
    accountant_id = serializers.UUIDField(required=True)
    reason = serializers.CharField(max_length=500, required=False, allow_blank=True)
    
    def validate_accountant_id(self, value):
        from apps.authentication.models import User
        try:
            accountant = User.objects.get(id=value, role='accountant', is_active=True)
            return accountant
        except User.DoesNotExist:
            raise serializers.ValidationError("Invalid accountant ID or accountant is not active.")

