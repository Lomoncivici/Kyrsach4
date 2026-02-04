from django.urls import path

from employees.decorators import check_employee_role, employee_required
from . import views

urlpatterns = [
    path('login/', views.employee_login, name='employee_login'),
    path('logout/', views.employee_logout, name='employee_logout'),
    path('admin-panel/', views.admin_panel, name='admin_panel'),
    path('analytics/', views.analytics_panel, name='analytics_panel'),
    path('analytics/export/', views.export_analytics, name='export_analytics'),
    path('support/', views.support_panel, name='support_panel'),
    path('no-role/', views.no_role_panel, name='no_role_panel'),

    path('admin/content/', views.admin_content_list, name='admin_content_list'),
    path('admin/content/add/', views.admin_content_add, name='admin_content_add'),
    path('admin/content/edit/<uuid:content_id>/', views.admin_content_edit, name='admin_content_edit'),
    path('admin/content/delete/<uuid:content_id>/', views.admin_content_delete, name='admin_content_delete'),
    path('admin/genres/', views.admin_genres, name='admin_genres'),
    path('admin/seasons/', views.admin_seasons_management, name='admin_seasons_management'),
    path('admin/media-assets/', views.admin_media_assets, name='admin_media_assets'),

    path('admin/seasons/add/<uuid:series_id>/', views.admin_season_add, name='admin_season_add'),
    path('admin/seasons/<uuid:season_id>/', views.admin_season_detail, name='admin_season_detail'),
    path('admin/seasons/<uuid:season_id>/delete/', views.admin_season_delete, name='admin_season_delete'),
    path('admin/episodes/add/<uuid:season_id>/', views.admin_episode_add, name='admin_episode_add'),
    path('admin/episodes/edit/<uuid:episode_id>/', views.admin_episode_edit, name='admin_episode_edit'),
    path('admin/episodes/<uuid:episode_id>/delete/', views.admin_episode_delete, name='admin_episode_delete'),

    path('admin/subscriptions/', views.admin_subscriptions, name='admin_subscriptions'),
    path('admin/subscriptions/create/', views.admin_subscription_create, name='admin_subscription_create'),
    path('admin/subscriptions/edit/<uuid:plan_id>/', views.admin_subscription_edit, name='admin_subscription_edit'),
    path('admin/subscriptions/delete/<uuid:plan_id>/', views.admin_subscription_delete, name='admin_subscription_delete'),
    path('admin/subscriptions/toggle/<uuid:plan_id>/', views.admin_subscription_toggle, name='admin_subscription_toggle'),

    path('admin/user-subscriptions/', views.admin_user_subscriptions, name='admin_user_subscriptions'),
    path('admin/user-subscriptions/grant/', views.admin_grant_subscription, name='admin_grant_subscription'),
    path('admin/user-subscriptions/edit/<uuid:sub_id>/', views.admin_user_subscription_edit, name='admin_user_subscription_edit'),
    path('admin/user-subscriptions/delete/<uuid:sub_id>/', views.admin_user_subscription_delete, name='admin_user_subscription_delete'),
    path('admin/user-subscriptions/extend/<uuid:sub_id>/', views.admin_user_subscription_extend, name='admin_user_subscription_extend'),

    path('admin/payments/', views.admin_payments, name='admin_payments'),
    path('admin/payments/update/<uuid:payment_id>/', views.admin_payment_update, name='admin_payment_update'),
    path('admin/payments/', views.admin_payments, name='admin_payments'),
    path('admin/subscriptions/export/', views.export_subscriptions, name='export_subscriptions'),

    # Управление пользователями
    path('admin/users/', views.admin_users_list, name='admin_users_list'),
    path('admin/users/create/', views.admin_user_create, name='admin_user_create'),
    path('admin/users/<uuid:user_id>/edit/', views.admin_user_edit, name='admin_user_edit'),
    path('admin/users/<uuid:user_id>/delete/', views.admin_user_delete, name='admin_user_delete'),
    path('admin/users/<uuid:user_id>/toggle/', views.admin_user_toggle_status, name='admin_user_toggle_status'),
    path('admin/users/<uuid:user_id>/reset-password/', views.admin_user_reset_password, name='admin_user_reset_password'),
    path('admin/users/<uuid:user_id>/activity/', views.admin_user_activity, name='admin_user_activity'),
    
    # Управление сотрудниками
    path('admin/employees/', views.admin_employees_list, name='admin_employees_list'),
    path('admin/employees/create/', views.admin_employee_create, name='admin_employee_create'),
    path('admin/employees/<uuid:employee_id>/edit/', views.admin_employee_edit, name='admin_employee_edit'),
    path('admin/employees/<uuid:employee_id>/delete/', views.admin_employee_delete, name='admin_employee_delete'),
    path('admin/employees/<uuid:employee_id>/toggle/', views.admin_employee_toggle_status, name='admin_employee_toggle_status'),
    path('admin/employees/<uuid:employee_id>/reset-password/', views.admin_employee_reset_password, name='admin_employee_reset_password'),

    # Управление покупками контента
    path('admin/purchases/', views.admin_user_purchases, name='admin_user_purchases'),
    path('admin/purchases/grant/', views.admin_grant_purchase, name='admin_grant_purchase'),
    path('admin/purchases/<str:purchase_id>/delete/', views.admin_purchase_delete, name='admin_purchase_delete'),
    path('admin/purchases/<str:purchase_id>/refund/', views.admin_purchase_refund, name='admin_purchase_refund'),
    path('admin/purchases/export/', views.export_purchases, name='export_purchases'),
]