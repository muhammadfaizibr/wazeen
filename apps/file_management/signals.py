from django.db.models.signals import post_delete, pre_delete
from django.dispatch import receiver
from .models import File
from .storage import secure_file_storage


@receiver(pre_delete, sender=File)
def delete_file_on_model_delete(sender, instance, **kwargs):
    """Delete physical files when File model is deleted"""
    try:
        # Delete main file
        if instance.file_path:
            secure_file_storage.delete_file(instance.file_path)
        
        # Delete preview file
        if instance.preview_path:
            secure_file_storage.delete_file(instance.preview_path)
        
        # Delete thumbnail
        if instance.thumbnail_path:
            secure_file_storage.delete_file(instance.thumbnail_path)
    except Exception:
        # Log error but don't prevent deletion
        pass