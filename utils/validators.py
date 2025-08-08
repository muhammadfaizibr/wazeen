import re
import os
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.utils.translation import gettext_lazy as _
from django.conf import settings


def validate_phone_number(value):
    """Validate phone number format"""
    if not value:
        return
    
    # Remove all non-digit characters except +
    cleaned = re.sub(r'[^\d+]', '', value)
    
    # Check if it starts with + and has 10-15 digits
    phone_regex = r'^\+?[1-9]\d{9,14}$'
    
    if not re.match(phone_regex, cleaned):
        raise ValidationError(
            _('Enter a valid phone number. Format: +1234567890 or 1234567890'),
            code='invalid'
        )


def validate_file_size(value, max_size_mb=10):
    """Validate file size"""
    if value.size > max_size_mb * 1024 * 1024:
        raise ValidationError(
            _(f'File size cannot exceed {max_size_mb}MB.'),
            code='file_too_large'
        )


def validate_image_dimensions(value, max_width=2048, max_height=2048):
    """Validate image dimensions"""
    try:
        from PIL import Image
        
        img = Image.open(value)
        width, height = img.size
        
        if width > max_width or height > max_height:
            raise ValidationError(
                _(f'Image dimensions cannot exceed {max_width}x{max_height} pixels.'),
                code='image_too_large'
            )
    except Exception:
        # If we can't open the image, let other validators handle it
        pass


class FileValidator:
    """Comprehensive file validator"""
    
    ALLOWED_EXTENSIONS = {
        'images': ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp'],
        'documents': ['pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'txt', 'rtf'],
        'archives': ['zip', 'rar', '7z', 'tar', 'gz'],
        'all': ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp', 'pdf', 'doc', 'docx', 
               'xls', 'xlsx', 'ppt', 'pptx', 'txt', 'rtf', 'zip', 'rar', '7z', 'tar', 'gz']
    }
    
    DANGEROUS_EXTENSIONS = [
        'exe', 'bat', 'cmd', 'scr', 'pif', 'vbs', 'js', 'jar', 'com', 'reg'
    ]
    
    def __init__(self, allowed_types='all', max_size_mb=10, max_dimensions=(2048, 2048)):
        self.allowed_extensions = self.ALLOWED_EXTENSIONS.get(allowed_types, self.ALLOWED_EXTENSIONS['all'])
        self.max_size_mb = max_size_mb
        self.max_dimensions = max_dimensions
    
    def __call__(self, value):
        # Check file extension
        ext = os.path.splitext(value.name)[1][1:].lower()
        
        if ext in self.DANGEROUS_EXTENSIONS:
            raise ValidationError(
                _('This file type is not allowed for security reasons.'),
                code='dangerous_file_type'
            )
        
        if ext not in self.allowed_extensions:
            raise ValidationError(
                _(f'File extension "{ext}" is not allowed. Allowed types: {", ".join(self.allowed_extensions)}'),
                code='invalid_extension'
            )
        
        # Check file size
        validate_file_size(value, self.max_size_mb)
        
        # Check image dimensions if it's an image
        if ext in self.ALLOWED_EXTENSIONS['images']:
            validate_image_dimensions(value, *self.max_dimensions)


def validate_password_strength(password):
    """Validate password strength"""
    if len(password) < 8:
        raise ValidationError(
            _('Password must be at least 8 characters long.'),
            code='password_too_short'
        )
    
    if not re.search(r'[A-Z]', password):
        raise ValidationError(
            _('Password must contain at least one uppercase letter.'),
            code='password_no_upper'
        )
    
    if not re.search(r'[a-z]', password):
        raise ValidationError(
            _('Password must contain at least one lowercase letter.'),
            code='password_no_lower'
        )
    
    if not re.search(r'\d', password):
        raise ValidationError(
            _('Password must contain at least one digit.'),
            code='password_no_digit'
        )
    
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        raise ValidationError(
            _('Password must contain at least one special character.'),
            code='password_no_special'
        )


def validate_hex_color(value):
    """Validate hex color format"""
    if not re.match(r'^#([A-Fa-f0-9]{6}|[A-Fa-f0-9]{3})$', value):
        raise ValidationError(
            _('Enter a valid hex color code (e.g., #FFFFFF or #FFF).'),
            code='invalid_hex_color'
        )


def validate_json_structure(value, required_keys=None):
    """Validate JSON structure"""
    if not isinstance(value, dict):
        raise ValidationError(
            _('Value must be a valid JSON object.'),
            code='invalid_json'
        )
    
    if required_keys:
        missing_keys = set(required_keys) - set(value.keys())
        if missing_keys:
            raise ValidationError(
                _(f'Missing required keys: {", ".join(missing_keys)}'),
                code='missing_json_keys'
            )


def validate_uuid_list(value):
    """Validate list of UUIDs"""
    import uuid
    
    if not isinstance(value, list):
        raise ValidationError(
            _('Value must be a list of UUIDs.'),
            code='invalid_uuid_list'
        )
    
    for item in value:
        try:
            uuid.UUID(str(item))
        except ValueError:
            raise ValidationError(
                _(f'"{item}" is not a valid UUID.'),
                code='invalid_uuid'
            )


def validate_business_email(value):
    """Validate business email (no common free email providers)"""
    free_email_domains = [
        'gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com',
        'aol.com', 'icloud.com', 'mail.com', 'yandex.com'
    ]
    
    domain = value.split('@')[1].lower()
    if domain in free_email_domains:
        raise ValidationError(
            _('Please use a business email address.'),
            code='free_email_not_allowed'
        )


def validate_arabic_text(value):
    """Validate Arabic text"""
    arabic_pattern = re.compile(r'[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]+')
    
    if not arabic_pattern.search(value):
        raise ValidationError(
            _('Text must contain Arabic characters.'),
            code='no_arabic_text'
        )


class TagsValidator:
    """Validate tags list"""
    
    def __init__(self, max_tags=10, max_tag_length=50):
        self.max_tags = max_tags
        self.max_tag_length = max_tag_length
    
    def __call__(self, value):
        if not isinstance(value, list):
            raise ValidationError(
                _('Tags must be a list.'),
                code='invalid_tags_format'
            )
        
        if len(value) > self.max_tags:
            raise ValidationError(
                _(f'Maximum {self.max_tags} tags allowed.'),
                code='too_many_tags'
            )
        
        for tag in value:
            if not isinstance(tag, str):
                raise ValidationError(
                    _('Each tag must be a string.'),
                    code='invalid_tag_type'
                )
            
            if len(tag.strip()) == 0:
                raise ValidationError(
                    _('Empty tags are not allowed.'),
                    code='empty_tag'
                )
            
            if len(tag) > self.max_tag_length:
                raise ValidationError(
                    _(f'Tag "{tag}" exceeds maximum length of {self.max_tag_length} characters.'),
                    code='tag_too_long'
                )