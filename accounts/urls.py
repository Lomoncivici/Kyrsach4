from django.urls import path
from . import views

urlpatterns = [
    path('login/', views.signin, name='login'),
    path('logout/', views.signout, name='logout'),
    path('register/', views.signup, name='register'),
    path('profile/', views.profile, name='profile'),

    # Смена пароля (старый пароль известен)
    path('password/change/', views.password_change, name='password_change'),

    # Сброс пароля (забыл пароль)
    path('password/reset/code/', views.password_reset_code, name='password_reset_code'),
    
    # Удаление аккаунта
    path('account/delete/', views.account_delete_request, name='account_delete_request'),
    path('account/delete/confirm/<uidb64>/<token>/', views.account_delete_confirm, name='account_delete_confirm'),

    # Сброс пароля для авторизованных
    path('password/reset/', views.password_reset_request, name='password_reset_request'),
    path('password/reset/confirm/', views.password_reset_confirm, name='password_reset_confirm'),

    # Сброс пароля для НЕавторизованных
    path('password/forgot/', views.forgot_password_request, name='forgot_password_request'),
    path('password/forgot/reset/<uuid:token>/', views.forgot_password_reset, name='forgot_password_reset'),
]