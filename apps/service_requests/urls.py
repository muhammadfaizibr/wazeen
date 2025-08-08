from django.urls import path, include
from . import views

app_name = 'service_requests'

urlpatterns = [
    # Categories
    path('categories/', views.ServiceRequestCategoryListView.as_view(), name='category_list'),
    
    # Service Requests
    path('', views.ServiceRequestListCreateView.as_view(), name='request_list_create'),
    path('<uuid:pk>/', views.ServiceRequestDetailView.as_view(), name='request_detail'),
    path('<uuid:request_id>/assign/', views.assign_request, name='assign_request'),
    path('<uuid:request_id>/status/', views.update_status, name='update_status'),
    
    # Notes
    path('<uuid:request_id>/notes/', views.RequestNoteListCreateView.as_view(), name='note_list_create'),
    
    # Dashboard
    path('dashboard/stats/', views.dashboard_stats, name='dashboard_stats'),
]