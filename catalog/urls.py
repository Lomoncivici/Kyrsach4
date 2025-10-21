from django.urls import path
from . import views

urlpatterns = [
    path('', views.main, name='main'),
    path('content/<uuid:pk>/', views.content_detail, name='content_detail'),
]
