from django.contrib import admin
from django.urls import path
from django.views.generic import RedirectView

from catalog import views as catalog_views
from accounts import views as accounts_views

urlpatterns = [
    path('admin/', admin.site.urls),

    path('', catalog_views.main, name='main'),
    path('content/<uuid:pk>/', catalog_views.content_detail, name='content_detail'),

    path('login/',  accounts_views.signin,  name='login'),
    path('logout/', accounts_views.signout, name='logout'),
    path('register/', accounts_views.signup, name='register'),
    path('profile/',  accounts_views.profile, name='profile'),

    path('account', RedirectView.as_view(pattern_name='profile', permanent=False), name='account')
]