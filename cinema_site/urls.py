from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView

from catalog import views as catalog_views
from accounts import views as accounts_views
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('employees/', include('employees.urls')),
    path('accounts/', include('accounts.urls')),

    path('', catalog_views.main, name='main'),
    path('content/<uuid:pk>/', catalog_views.content_detail, name='content_detail'),
    path("", include(("catalog.urls", "catalog"), namespace="catalog")),

    path("api/v1/", include(("api.urls", "api"), namespace="api")),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    
    path('', include('cinemaapp.urls', namespace='cinemaapp')),

    path('login/',  accounts_views.signin,  name='login'),
    path('logout/', accounts_views.signout, name='logout'),
    path('register/', accounts_views.signup, name='register'),
    path('profile/',  accounts_views.profile, name='profile'),

    path('account', RedirectView.as_view(pattern_name='profile', permanent=False), name='account'),

    path("api/token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),

    path('account', RedirectView.as_view(pattern_name='catalog:subscriptions', permanent=False), name='account'),
    path('subscribe/', RedirectView.as_view(pattern_name='catalog:subscriptions', permanent=False), name='subscribe'),
]