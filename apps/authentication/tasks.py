# apps/authentication/tasks.py

from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings


from celery import shared_task

@shared_task
def send_verification_email_task(user_id, email, token_str, first_name=None, username=None):
    """Send email verification email asynchronously"""
    subject = 'Verify your email address'
    verification_url = f"{settings.FRONTEND_URL}/verify-email/{token_str}"
    
    context = {
        'user': {
            'first_name': first_name,
            'username': username
        },
        'verification_url': verification_url,
        'site_name': 'Wazeens'
    }
    
    # Changed from 'emails/email_verification.html' to:
    html_message = render_to_string('authentication/emails/email_verification.html', context)
    
    send_mail(
        subject=subject,
        message='',
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[email],
        html_message=html_message,
        fail_silently=False,
    )

@shared_task
def send_password_reset_email_task(user_email, token, first_name=None, username=None):
    subject = 'Reset your password'
    reset_url = f"{settings.FRONTEND_URL}/reset-password/{token}"
    
    context = {
        'user': {
            'first_name': first_name,
            'username': username
        },
        'reset_url': reset_url,
        'site_name': 'Wazeen',
    }
    
    # Changed from 'emails/password_reset.html' to:
    html_message = render_to_string('authentication/emails/password_reset.html', context)
    
    send_mail(
        subject=subject,
        message='',
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user_email],
        html_message=html_message,
        fail_silently=False,
    )