from django.urls import path
from . import views
from . import actions

app_name = "catalog"

urlpatterns = [
    path('', views.main, name='main'),
    path('content/<uuid:pk>/', views.content_detail, name='content_detail'),
    path("content/<uuid:pk>/rate/", views.rate_content, name="rate_content"),
    path("content/<uuid:pk>/play/", views.movie_source, name="movie_source"),
    path('subscribe/', views.subscriptions_view, name='subscribe'),
    path("account/", views.account, name="account"),
    path("me/", views.my_page, name="my_page"),
    path("purchase/<uuid:pk>/start/", views.purchase_start, name="purchase_start"),
    path('content/<uuid:pk>/rate/', views.rate_content, name='content_rate'),
    path('content/<uuid:pk>/watchlist-toggle/', views.watchlist_toggle, name='watchlist_toggle'),
    path('content/<uuid:pk>/season/<int:sn>/episode/<int:en>/play/', views.episode_source, name='episode_source'),
    path('content/<uuid:content_id>/favorite/', actions.toggle_favorite, name='favorite_toggle'),
    path('content/<uuid:content_id>/favorite/status/', actions.favorite_status, name='favorite_status'),

    # Покупки и подписки
    path('purchase/<uuid:pk>/confirm/', views.purchase_content, name='purchase_content'),
    path('subscriptions/activate/<str:plan_code>/', views.activate_subscription, name='activate_subscription'),
    path('subscription/cancel/', views.cancel_subscription, name='cancel_subscription'),
    path('subscription/<str:plan_code>/process/', views.process_subscription_payment, 
         name='process_subscription_payment'),
    path('purchase/<uuid:pk>/process/', views.process_payment, name='process_payment'),

    # Поисковая строка
    path('search/', views.search, name='search'),

    path('rutube/embed/<str:video_id>/', views.rutube_embed_page, name='rutube_embed'),
]
