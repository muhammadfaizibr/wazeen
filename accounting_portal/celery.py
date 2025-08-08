import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'accounting_portal.settings.base')

app = Celery('accounting_portal')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()
