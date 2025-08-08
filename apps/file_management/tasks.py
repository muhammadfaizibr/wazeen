from celery import shared_task
from django.core.files.storage import default_storage
from PIL import Image
import os
import subprocess
from .models import File
from .storage import secure_file_storage


@shared_task(bind=True, max_retries=3)
def generate_file_preview(self, file_id):
    """Generate file preview and thumbnail"""
    try:
        file_obj = File.objects.get(id=file_id)
        file_obj.preview_status = 'processing'
        file_obj.save()
        
        file_path = secure_file_storage.get_file_path(file_obj.file_path)
        
        # Generate thumbnail for images
        if file_obj.is_image:
            thumbnail_path = generate_image_thumbnail(file_path, file_obj.stored_filename)
            if thumbnail_path:
                file_obj.thumbnail_path = thumbnail_path
        
        # Generate preview for documents
        if file_obj.is_document:
            preview_path = generate_document_preview(file_path, file_obj.stored_filename)
            if preview_path:
                file_obj.preview_path = preview_path
        
        file_obj.preview_status = 'ready'
        file_obj.save()
        
    except File.DoesNotExist:
        pass
    except Exception as exc:
        file_obj = File.objects.get(id=file_id)
        file_obj.preview_status = 'failed'
        file_obj.save()
        
        # Retry with exponential backoff
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


def generate_image_thumbnail(file_path, stored_filename):
    """Generate thumbnail for image files"""
    try:
        with Image.open(file_path) as img:
            img.thumbnail((300, 300), Image.Resampling.LANCZOS)
            
            # Save thumbnail
            name, _ = os.path.splitext(stored_filename)
            thumbnail_filename = f"{name}_thumb.jpg"
            thumbnail_path = secure_file_storage.save_file_content(
                img, thumbnail_filename, 'image/jpeg'
            )
            
            return thumbnail_path
    except Exception:
        return None


def generate_document_preview(file_path, stored_filename):
    """Generate preview for document files"""
    try:
        # This would require additional tools like LibreOffice or pandoc
        # For PDF files, you might use pdf2image
        # For now, return None to indicate preview not supported
        
        if file_path.lower().endswith('.pdf'):
            # Could use pdf2image here to generate preview
            pass
        
        return None
    except Exception:
        return None
