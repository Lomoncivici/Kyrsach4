from django.shortcuts import render
from rest_framework import viewsets, mixins, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.db import connection
from django.shortcuts import get_object_or_404

from cinemaapp.models import Content
from cinemaapp import services
from .serializers import (
    ContentSerializer, RateSerializer,
    ProgressGetSerializer, ProgressPostSerializer,
    PurchaseCreateSerializer,
)
from .permissions import IsAdmin, IsSupport, IsFinance, ReadOnly

# ---------- Контент ----------
class ContentViewSet(mixins.ListModelMixin,
                     mixins.RetrieveModelMixin,
                     viewsets.GenericViewSet):
    queryset = Content.objects.select_related("cover_image", "trailer", "video").all()
    serializer_class = ContentSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        qs = super().get_queryset()
        q = self.request.query_params.get("q")
        ctype = self.request.query_params.get("type")  # movie/series
        if q:
            qs = qs.filter(title__icontains=q)
        if ctype:
            qs = qs.filter(type=ctype)
        return qs.order_by("-release_year", "title")

    @action(detail=True, methods=["get"], permission_classes=[AllowAny])
    def can_watch(self, request, pk=None):
        c = self.get_object()
        can = services.can_watch(request.user, c) if request.user.is_authenticated else bool(c.is_free)
        return Response({"ok": True, "can_watch": bool(can)})

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated])
    def rate(self, request, pk=None):
        ser = RateSerializer(data=request.data); ser.is_valid(raise_exception=True)
        avg = services.upsert_rating(request.user, pk, ser.validated_data["value"])
        return Response({"ok": True, "avg": avg})

    @action(detail=True, methods=["get", "post"], url_path="progress", permission_classes=[IsAuthenticated])
    def progress(self, request, pk=None):
        if request.method.lower() == "get":
            sn = request.query_params.get("sn", 0)
            en = request.query_params.get("en", 0)
            data = services.get_progress(request.user, pk, sn, en)
            return Response({"ok": True, **data})
        # POST
        ser = ProgressPostSerializer(data=request.data); ser.is_valid(raise_exception=True)
        v = ser.validated_data
        services.save_progress(
            request.user, pk, v["position"], v.get("duration"),
            v.get("sn", 0), v.get("en", 0), v.get("completed", False)
        )
        return Response({"ok": True}, status=status.HTTP_200_OK)

    @action(detail=True, methods=["get"], url_path="source", permission_classes=[IsAuthenticated])
    def source(self, request, pk=None):
        """Единая точка получения источника видео (movie/series). Возвращает kind + url."""
        c = self.get_object()
        if not services.can_watch(request.user, c) and not c.is_free:
            return Response({"ok": False, "reason": "forbidden"}, status=403)

        if c.type == "movie":

            url = c.video.url if getattr(c, "video", None) else ""
            kind = "youtube" if "youtu" in (url or "").lower() else ("rutube" if "rutube" in (url or "").lower() else "file")
            return Response({"ok": True, "kind": kind, "url": url})

        return Response({"ok": False, "reason": "provide sn/en"}, status=400)

    @action(detail=True, methods=["get"], url_path=r"episode-source", permission_classes=[IsAuthenticated])
    def episode_source(self, request, pk=None):
        sn = request.query_params.get("sn")
        en = request.query_params.get("en")
        if not sn or not en:
            return Response({"ok": False, "reason": "sn/en required"}, status=400)

        c = self.get_object()
        if not services.can_watch(request.user, c) and not c.is_free:
            return Response({"ok": False, "reason": "forbidden"}, status=403)
        data = services.episode_source(c, int(sn), int(en))  # добавь у себя этот метод если нужно
        return Response({"ok": True, **data})


# ---------- Покупки ----------
class PurchaseViewSet(mixins.ListModelMixin,
                      mixins.CreateModelMixin,
                      viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = PurchaseCreateSerializer

    def list(self, request):
        rows = services.list_user_purchases(request.user)
        return Response({"ok": True, "items": rows})

    def create(self, request):
        ser = PurchaseCreateSerializer(data=request.data); ser.is_valid(raise_exception=True)
        content_id = ser.validated_data["content_id"]

        cid = services._ensure_cinema_user(request.user)
        with connection.cursor() as cur:
            cur.execute("""
                INSERT INTO cinema.purchases(user_id, content_id, purchased_at)
                VALUES (%s, %s, now())
                ON CONFLICT DO NOTHING
            """, [cid, str(content_id)])
        return Response({"ok": True}, status=201)


# ---------- "Моё" ----------
from rest_framework.views import APIView

class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({"ok": True, "user": request.user.username})

class MePurchases(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        return Response({"ok": True, "items": services.list_user_purchases(request.user)})

class MeRatings(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        return Response({"ok": True, "items": services.list_user_ratings(request.user)})

class MeHistory(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        return Response({"ok": True, "items": services.list_user_history(request.user)})