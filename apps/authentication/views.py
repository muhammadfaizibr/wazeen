from rest_framework import generics, status, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView
from django.contrib.auth import update_session_auth_hash
from django.utils import timezone
from datetime import timedelta
from django.core.mail import send_mail
from django.conf import settings
from django.template.loader import render_to_string

from apps.authentication.models import User, UserProfile, EmailVerificationToken, PasswordResetToken
from apps.authentication.serializers import (
    CustomTokenObtainPairSerializer,
    UserRegistrationSerializer,
    UserSerializer,
    UserProfileSerializer,
    PasswordChangeSerializer,
    PasswordResetRequestSerializer,
    PasswordResetConfirmSerializer,
    EmailVerificationSerializer
)
from apps.authentication.tasks import send_verification_email_task, send_password_reset_email_task


class CustomTokenObtainPairView(TokenObtainPairView):
    """Custom JWT token view with additional user data"""
    serializer_class = CustomTokenObtainPairSerializer


class UserRegistrationView(generics.CreateAPIView):
    """User registration view"""
    queryset = User.objects.all()
    serializer_class = UserRegistrationSerializer
    permission_classes = [permissions.AllowAny]
    
    def perform_create(self, serializer):
        user = serializer.save()
        token = EmailVerificationToken.objects.create(
            user=user,
            expires_at=timezone.now() + timedelta(hours=24)
        )

        # 👇 Asynchronously send email
        send_verification_email_task.delay(
            user_id=user.id,
            email=user.email,
            token_str=str(token.token),
            first_name=user.first_name,
            username=user.username
        )
    


class UserProfileView(generics.RetrieveUpdateAPIView):
    """User profile view"""
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_object(self):
        return self.request.user


class UserProfileDetailView(generics.RetrieveUpdateAPIView):
    """User profile detail view"""
    serializer_class = UserProfileSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_object(self):
        profile, created = UserProfile.objects.get_or_create(user=self.request.user)
        return profile


class PasswordChangeView(generics.GenericAPIView):
    """Password change view"""
    serializer_class = PasswordChangeSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        user = request.user
        user.set_password(serializer.validated_data['new_password'])
        user.save()
        
        # Keep user logged in after password change
        update_session_auth_hash(request, user)
        
        return Response({
            'detail': 'Password changed successfully.'
        }, status=status.HTTP_200_OK)


class PasswordResetRequestView(generics.GenericAPIView):
    """Password reset request view"""
    serializer_class = PasswordResetRequestSerializer
    permission_classes = [permissions.AllowAny]
    
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        email = serializer.validated_data['email']
        user = User.objects.get(email=email, is_active=True)
        
        # Create password reset token
        token = PasswordResetToken.objects.create(
            user=user,
            expires_at=timezone.now() + timedelta(hours=2)
        )
        
        # Send reset email via Celery
        send_password_reset_email_task.delay(
            user_email=user.email,
            token=str(token.token),
            first_name=user.first_name,
            username=user.username
        )
        return Response({
            'detail': 'Password reset email sent.'
        }, status=status.HTTP_200_OK)

class PasswordResetConfirmView(generics.GenericAPIView):
    """Password reset confirmation view"""
    serializer_class = PasswordResetConfirmSerializer
    permission_classes = [permissions.AllowAny]
    
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        token_uuid = serializer.validated_data['token']
        new_password = serializer.validated_data['new_password']
        
        try:
            token = PasswordResetToken.objects.get(
                token=token_uuid,
                used=False
            )
            
            if token.is_expired():
                return Response({
                    'error': 'Token has expired.'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Reset password
            user = token.user
            user.set_password(new_password)
            user.save()
            
            # Mark token as used
            token.used = True
            token.save()
            
            return Response({
                'detail': 'Password reset successful.'
            }, status=status.HTTP_200_OK)
            
        except PasswordResetToken.DoesNotExist:
            return Response({
                'error': 'Invalid token.'
            }, status=status.HTTP_400_BAD_REQUEST)
        


class EmailVerificationView(generics.GenericAPIView):
    """Email verification view"""
    serializer_class = EmailVerificationSerializer
    permission_classes = [permissions.AllowAny]
    
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        token_uuid = serializer.validated_data['token']
        
        try:
            token = EmailVerificationToken.objects.get(
                token=token_uuid,
                used=False
            )
            
            if token.is_expired():
                return Response({
                    'error': 'Token has expired.'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Verify email
            user = token.user
            user.email_verified = True
            user.save()
            
            # Mark token as used
            token.used = True
            token.save()
            
            return Response({
                'detail': 'Email verified successfully.'
            }, status=status.HTTP_200_OK)
            
        except EmailVerificationToken.DoesNotExist:
            return Response({
                'error': 'Invalid token.'
            }, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def resend_verification_email(request):
    """Resend email verification"""
    user = request.user
    
    if user.email_verified:
        return Response({
            'error': 'Email is already verified.'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    # Create new verification token
    token = EmailVerificationToken.objects.create(
        user=user,
        expires_at=timezone.now() + timedelta(hours=24)
    )
    
    # Send verification email
    subject = 'Verify your email address'
    verification_url = f"{settings.FRONTEND_URL}/verify-email/{token.token}"
    
    context = {
        'user': user,
        'verification_url': verification_url,
        'site_name': 'Accounting Portal'
    }
    
    html_message = render_to_string('emails/email_verification.html', context)
    
    send_mail(
        subject=subject,
        message='',
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        html_message=html_message,
        fail_silently=False,
    )
    
    return Response({
        'detail': 'Verification email sent.'
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def user_status(request):
    """Get current user status"""
    user = request.user
    user.update_last_activity()
    
    return Response({
        'id': str(user.id),
        'email': user.email,
        'full_name': user.full_name,
        'role': user.role,
        'email_verified': user.email_verified,
        'preferred_language': user.preferred_language,
        'is_online': True,
        'last_activity': user.last_activity,
        'avatar': user.avatar.url if user.avatar else None,
    })

