from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ContentViewSet,
    PurchaseViewSet,
    MeView, MeDetailsView,
    SubscriptionViewSet,
    PaymentViewSet,
    FavoriteViewSet,
    home_data,
    search_content
)

router = DefaultRouter()
router.register(r"content", ContentViewSet, basename="content")
router.register(r"purchases", PurchaseViewSet, basename="purchases")
router.register(r"subscriptions", SubscriptionViewSet, basename="subscriptions")
router.register(r"payments", PaymentViewSet, basename="payments")
router.register(r"favorites", FavoriteViewSet, basename="favorites")

urlpatterns = [
    path("", include(router.urls)),
    path('api/v1/', include(router.urls)),
    path("me/", MeView.as_view(), name="me"),

    path("me/<str:detail_type>/", MeDetailsView.as_view(), name="me-details"),
    path("home/", home_data, name="home-data"),
    path("search/", search_content, name="search-content"),
]