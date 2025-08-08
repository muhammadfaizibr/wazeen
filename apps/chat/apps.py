# apps/file_management/apps.py
from django.apps import AppConfig

class ChatConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.chat'  # Corrected to include the full path
    verbose_name = 'Chat'
