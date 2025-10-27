from django.urls import path
from .views import content_favorite_toggle, content_favorite_check

app_name = 'cinemaapp'

urlpatterns = [
    path('content/<uuid:pk>/favorite/', content_favorite_toggle, name='content_favorite_toggle'),
    path('content/<uuid:pk>/favorite/check/', content_favorite_check, name='content_favorite_check'),
]