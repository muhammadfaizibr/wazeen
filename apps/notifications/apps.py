# apps/file_management/apps.py
from django.apps import AppConfig

class NotificatioConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.notifications'  # Corrected to include the full path
    verbose_name = 'Notifications'
