# core/urls.py
from django.contrib import admin
from django.urls import path, include
from django.views.generic import TemplateView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/authentication/', include('apps.authentication.urls')),
    path('api/service-requests/', include('apps.service_requests.urls')),
    path('api/file-management/', include('apps.file_management.urls')),
    path('api/chat/', include('apps.chat.urls')),
    # path('api/notifications/', include('apps.notifications.urls')),
    # path('api/analytics/', include('apps.analytics.urls')),
    # path('api/reviews/', include('apps.reviews.urls')),
    path('', TemplateView.as_view(template_name='index.html'), name='home'),
]
