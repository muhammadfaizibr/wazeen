from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, UserProfile, EmailVerificationToken, PasswordResetToken

class CustomUserAdmin(UserAdmin):
    """Custom admin interface for User model"""
    model = User
    list_display = ('email', 'full_name', 'role', 'is_active', 'is_staff', 'last_activity')
    list_filter = ('role', 'is_active', 'is_staff', 'preferred_language')
    search_fields = ('email', 'first_name', 'last_name')
    ordering = ('email',)
    
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Personal info', {'fields': ('first_name', 'last_name', 'phone_number', 'preferred_language', 'avatar')}),
        ('Permissions', {'fields': ('role', 'is_active', 'is_staff', 'is_superuser')}),
        ('Important dates', {'fields': ('last_activity', 'created_at', 'updated_at')}),
    )
    
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'first_name', 'last_name', 'role', 'password1', 'password2'),
        }),
    )
    
    readonly_fields = ('created_at', 'updated_at', 'last_activity')
    filter_horizontal = ()
    list_per_page = 25

class UserProfileAdmin(admin.ModelAdmin):
    """Admin interface for UserProfile model"""
    list_display = ('user', 'company', 'job_title', 'city', 'country')
    search_fields = ('user__email', 'company', 'job_title', 'city', 'country')
    list_filter = ('country', 'city')
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        (None, {'fields': ('user',)}),
        ('Profile info', {'fields': ('bio', 'company', 'job_title', 'address', 'city', 'country', 'timezone')}),
        ('Notifications', {'fields': ('notification_preferences',)}),
        ('Timestamps', {'fields': ('created_at', 'updated_at')}),
    )

class EmailVerificationTokenAdmin(admin.ModelAdmin):
    """Admin interface for EmailVerificationToken model"""
    list_display = ('user', 'token', 'created_at', 'expires_at', 'used')
    search_fields = ('user__email', 'token')
    list_filter = ('used',)
    readonly_fields = ('created_at', 'expires_at', 'token')
    
    fieldsets = (
        (None, {'fields': ('user', 'token')}),
        ('Status', {'fields': ('used',)}),
        ('Timestamps', {'fields': ('created_at', 'expires_at')}),
    )

class PasswordResetTokenAdmin(admin.ModelAdmin):
    """Admin interface for PasswordResetToken model"""
    list_display = ('user', 'token', 'created_at', 'expires_at', 'used')
    search_fields = ('user__email', 'token')
    list_filter = ('used',)
    readonly_fields = ('created_at', 'expires_at', 'token')
    
    fieldsets = (
        (None, {'fields': ('user', 'token')}),
        ('Status', {'fields': ('used',)}),
        ('Timestamps', {'fields': ('created_at', 'expires_at')}),
    )

# Register models with admin site
admin.site.register(User, CustomUserAdmin)
admin.site.register(UserProfile, UserProfileAdmin)
admin.site.register(EmailVerificationToken, EmailVerificationTokenAdmin)
admin.site.register(PasswordResetToken, PasswordResetTokenAdmin)