from django.db.models.signals import post_save
from django.dispatch import receiver
from apps.chat.models import ChatRoom
from apps.service_requests.models import ServiceRequest

@receiver(post_save, sender=ServiceRequest)
def create_chat_room(sender, instance, created, **kwargs):
    """Automatically create a chat room when a new service request is created"""
    if created:  # Only for new instances
        ChatRoom.objects.get_or_create(
            request=instance,
            defaults={
                'is_active': True,
                'allow_file_sharing': True,
                'max_file_size': 52428800,  # 50MB
            }
        )