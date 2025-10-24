from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ContentViewSet,
    PurchaseViewSet,
    MeView, MePurchases, MeRatings, MeHistory
)

router = DefaultRouter()
router.register(r"content", ContentViewSet, basename="content")
router.register(r"purchases", PurchaseViewSet, basename="purchases")

urlpatterns = [
    path("", include(router.urls)),
    path("me/", MeView.as_view(), name="me"),
    path("me/purchases/", MePurchases.as_view(), name="me-purchases"),
    path("me/ratings/", MeRatings.as_view(), name="me-ratings"),
    path("me/history/", MeHistory.as_view(), name="me-history"),
]