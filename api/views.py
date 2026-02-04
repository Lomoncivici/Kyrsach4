from django.contrib.auth.decorators import login_required
from cinemaapp import models
from cinemaapp.models import Content
from django.utils import timezone
from django.shortcuts import render
from rest_framework import viewsets, mixins, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.db import connection
from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework.decorators import api_view, permission_classes
from cinemaapp.models import Content
from cinemaapp import services
from catalog.models import SubscriptionPlan, UserSubscription, Payment
from .serializers import (
    ContentSerializer, RateSerializer,
    ProgressGetSerializer, ProgressPostSerializer,
    PurchaseCreateSerializer,
)
from .permissions import IsAdmin, IsSupport, IsAnalyst, ReadOnly


@api_view(['GET'])
@permission_classes([AllowAny])
def home_data(request):
    """API для данных главной страницы"""
    from cinemaapp import services

    movies = services.list_content("movies", limit=20)
    series = services.list_content("series", limit=20)

    continue_items = []
    if request.user.is_authenticated:
        continue_items = services.get_continue_watch_for_user(request.user, limit=20)

    genre_sections_raw = []
    if hasattr(services, "build_genre_sections"):
        genre_sections_raw = services.build_genre_sections(limit_per_genre=20)
    else:

        try:
            genre_sections_raw = []
        except:
            pass

    all_ids = []
    for c in movies: all_ids.append(c.id)
    for c in series: all_ids.append(c.id)
    for c in continue_items: all_ids.append(c.id)
    for section in genre_sections_raw:
        for c in section.get("items", []):
            all_ids.append(c.id)
    
    ratings = services.rating_map(all_ids) if all_ids else {}

    def serialize_content(c):
        backdrop_url = ""
        if getattr(c, "cover_image_wide", None):
            backdrop_url = c.cover_image_wide.url if hasattr(c.cover_image_wide, 'url') else ""
        elif getattr(c, "cover_image", None):
            backdrop_url = c.cover_image.url if hasattr(c.cover_image, 'url') else ""
        
        return {
            "id": str(c.id),
            "title": c.title,
            "type": c.type,
            "poster_url": c.cover_image.url if c.cover_image and hasattr(c.cover_image, 'url') else "",
            "backdrop_url": backdrop_url,
            "release_year": c.release_year,
            "is_free": c.is_free,
            "rating": float(ratings.get(c.id, 0.0) or 0.0)
        }
    
    response_data = {
        "movies": [serialize_content(c) for c in movies],
        "series": [serialize_content(c) for c in series],
        "continue_watch": [serialize_content(c) for c in continue_items] if request.user.is_authenticated else [],
        "genre_sections": [
            {
                "title": section.get("title", "Жанр"),
                "items": [serialize_content(c) for c in section.get("items", [])]
            }
            for section in genre_sections_raw
        ]
    }
    
    return Response({"ok": True, "data": response_data})


@api_view(['GET'])
@permission_classes([AllowAny])
def search_content(request):
    """API для поиска контента"""
    from cinemaapp import services
    from cinemaapp.models import Content
    from django.db.models import Q
    import uuid
    
    query = request.GET.get('q', '').strip()
    content_type = request.GET.get('type', '').strip()
    
    if not query:
        return Response({"ok": True, "query": "", "results": []})
    
    qs = Content.objects.all().select_related('cover_image', 'cover_image_wide')
    

    try:

        content_id = uuid.UUID(query)
        qs = qs.filter(id=content_id)
    except (ValueError, AttributeError):

        qs = qs.filter(
            Q(title__icontains=query) | 
            Q(description__icontains=query)
        )
    
    if content_type:
        qs = qs.filter(type=content_type)
    
    results = qs.distinct()[:50]
    
    if not results and len(query) >= 8:
        qs = Content.objects.filter(
            Q(title__icontains=query) | 
            Q(description__icontains=query) |
            Q(id__icontains=query)
        )
        if content_type:
            qs = qs.filter(type=content_type)
        results = qs.distinct()[:50]

    content_ids = [c.id for c in results]
    ratings = services.rating_map(content_ids) if content_ids else {}
    

    def serialize_result(c):
        price = float(getattr(c, "price", 0) or 0)
        
        return {
            "id": str(c.id),
            "title": c.title,
            "type": c.type,
            "poster_url": c.cover_image.url if c.cover_image else "",
            "backdrop_url": (c.cover_image_wide.url if getattr(c, "cover_image_wide", None) 
                           else (c.cover_image.url if c.cover_image else "")),
            "release_year": c.release_year,
            "is_free": c.is_free,
            "rating": float(ratings.get(c.id, 0.0) or 0.0),
            "description": (c.description[:180] + "…") if len(c.description) > 180 else c.description,
            "full_description": c.description,
            "is_subscription": (not c.is_free) and (0 < price <= 1),
            "price": price
        }
    
    exact_match = None
    other_results = []
    
    for c in results:
        item = serialize_result(c)

        if item['title'].lower() == query.lower() or str(c.id) == query:
            exact_match = item

        elif item['title'].lower().startswith(query.lower()):
            if exact_match is None:
                exact_match = item
            else:
                other_results.append(item)
        else:
            other_results.append(item)

    if not exact_match and other_results:
        exact_match = other_results[0]
        other_results = other_results[1:]
    
    return Response({
        "ok": True,
        "query": query,
        "exact_match": exact_match,
        "results": other_results,
        "count": len(results)
    })

class ContentViewSet(mixins.ListModelMixin,
                     mixins.RetrieveModelMixin,
                     viewsets.GenericViewSet):
    queryset = Content.objects.select_related("cover_image_wide", "cover_image", "trailer", "video").all()
    serializer_class = ContentSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        qs = super().get_queryset()
        q = self.request.query_params.get("q")
        ctype = self.request.query_params.get("type")
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
        ser = RateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        
        try:
            avg = services.upsert_rating(request.user, pk, ser.validated_data["value"])
            return Response({"ok": True, "avg": avg})
        except Exception as e:
            if "Отзыв можно оставить только по доступному контенту" in str(e):
                return Response(
                    {"ok": False, "error": "Нет доступа к контенту для оценки"},
                    status=status.HTTP_403_FORBIDDEN
                )

            return Response(
                {"ok": False, "error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=["get", "post"], url_path="progress", permission_classes=[IsAuthenticated])
    def progress(self, request, pk=None):
        if request.method.lower() == "get":
            sn = request.query_params.get("sn", 0)
            en = request.query_params.get("en", 0)
            data = services.get_progress(request.user, pk, sn, en)
            return Response({"ok": True, **data})

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

    @action(detail=True, methods=["get"], url_path="episode-source", permission_classes=[AllowAny])
    def episode_source(self, request, pk=None):
        c = self.get_object()
        sn = request.query_params.get("sn") or request.query_params.get("season") or "1"
        en = request.query_params.get("en") or request.query_params.get("episode") or "1"
        def _to_int(val, default=1):
            try:
                return int(val)
            except (TypeError, ValueError):
                return default

        sn_i = _to_int(sn, 1)
        en_i = _to_int(en, 1)

        if not (c.is_free or services.can_watch(request.user, c)):
            return Response({"ok": False, "detail": "forbidden"}, status=403)

        data = services.episode_source(c, sn_i, en_i)
        status_code = 200 if data.get("ok") else 404
        return Response(data, status=status_code)
    
    @action(detail=True, methods=["get"], url_path="series-tree", permission_classes=[AllowAny])
    def series_tree(self, request, pk=None):
        """
        Вернёт дерево сезонов/эпизодов для сериалов.
        Формат: {"ok": True, "seasons":[{"number":1,"title":"Сезон 1","episodes":[{"number":1,"title":"Серия 1"}, ...]}]}
        """
        c = self.get_object()
        data = services.series_tree(c)
        return Response({"ok": True, "seasons": data})

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

class SubscriptionViewSet(viewsets.ViewSet):
    """API для управления подписками"""
    permission_classes = [IsAuthenticated]
    
    def list(self, request):
        """Получить информацию о подписках пользователя"""
        from cinemaapp import services
        from django.db.models import Sum

        try:
            from catalog.models import CinemaUser
            cinema_user = CinemaUser.objects.get(login=request.user.username)
        except CinemaUser.DoesNotExist:
            return Response(
                {"ok": False, "error": "Пользователь не найден в системе"},
                status=status.HTTP_404_NOT_FOUND
            )

        active_sub = None
        active_subs = UserSubscription.objects.filter(
            user=cinema_user,
            status='active',
            expires_at__gte=timezone.now()
        ).select_related('plan').order_by('-started_at')
        
        if active_subs.exists():
            active_sub = active_subs.first()
        
  
        all_subs = UserSubscription.objects.filter(
            user=cinema_user
        ).select_related('plan').order_by('-started_at')
        

        plans = SubscriptionPlan.objects.filter(is_active=True).order_by('price')
        

        total_count = UserSubscription.objects.filter(user=cinema_user).count()
        active_count = UserSubscription.objects.filter(
            user=cinema_user,
            status='active',
            expires_at__gte=timezone.now()
        ).count()


        total_spent_result = UserSubscription.objects.filter(
            user=cinema_user
        ).aggregate(total=Sum('plan__price'))
        total_spent = float(total_spent_result['total'] or 0)

        def serialize_subscription(sub):
            return {
                "id": str(sub.id),
                "plan": {
                    "id": str(sub.plan.id),
                    "name": sub.plan.name,
                    "code": sub.plan.code,
                    "price": float(sub.plan.price),
                    "period_months": sub.plan.period_months
                },
                "status": sub.status,
                "started_at": sub.started_at,
                "expires_at": sub.expires_at,
                "is_active": sub.is_actually_active if hasattr(sub, 'is_actually_active') else False,
                "days_left": sub.days_left if hasattr(sub, 'days_left') else 0,
                "can_be_cancelled": sub.can_be_cancelled if hasattr(sub, 'can_be_cancelled') else False,
                "will_be_extended": sub.will_be_extended if hasattr(sub, 'will_be_extended') else False
            }
        
        return Response({
            "ok": True,
            "active_subscription": serialize_subscription(active_sub) if active_sub else None,
            "subscriptions": [serialize_subscription(sub) for sub in all_subs],
            "plans": [
                {
                    "id": str(plan.id),
                    "name": plan.name,
                    "code": plan.code,
                    "price": float(plan.price),
                    "period_months": plan.period_months,
                    "description": f"{plan.name} - {plan.price} руб. за {plan.period_months} мес."
                }
                for plan in plans
            ],
            "stats": {
                "total_count": total_count,
                "active_count": active_count,
                "total_spent": total_spent
            }
        })
    
    @action(detail=False, methods=['post'])
    def activate(self, request):
        """Активировать подписку (начало процесса)"""
        plan_code = request.data.get('plan_code')
        
        if not plan_code:
            return Response(
                {"ok": False, "error": "Не указан plan_code"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            plan = SubscriptionPlan.objects.get(code=plan_code, is_active=True)
        except SubscriptionPlan.DoesNotExist:
            return Response(
                {"ok": False, "error": "План подписки не найден"},
                status=status.HTTP_404_NOT_FOUND
            )

        return Response({
            "ok": True,
            "plan": {
                "id": str(plan.id),
                "name": plan.name,
                "code": plan.code,
                "price": float(plan.price),
                "period_months": plan.period_months
            },
            "confirmation_url": f"/subscribe/activate/{plan.code}/"
        })
    
    @action(detail=False, methods=['post'])
    def cancel(self, request):
        """Отменить текущую активную подписку"""
        subscription_id = request.data.get('subscription_id')
        
        try:
            from catalog.models import CinemaUser
            cinema_user = CinemaUser.objects.get(login=request.user.username)
        except CinemaUser.DoesNotExist:
            return Response(
                {"ok": False, "error": "Пользователь не найден в системе"},
                status=status.HTTP_404_NOT_FOUND
            )

        if subscription_id:
            try:
                subscription = UserSubscription.objects.get(
                    id=subscription_id,
                    user=cinema_user,
                    status='active'
                )
            except UserSubscription.DoesNotExist:
                return Response(
                    {"ok": False, "error": "Подписка не найдена"},
                    status=status.HTTP_404_NOT_FOUND
                )
        else:
            subscription = UserSubscription.objects.filter(
                user=cinema_user,
                status='active',
                expires_at__gte=timezone.now()
            ).first()
        
        if not subscription:
            return Response(
                {"ok": False, "error": "Нет активной подписки для отмены"},
                status=status.HTTP_404_NOT_FOUND
            )

        if not subscription.can_be_cancelled:
            return Response(
                {"ok": False, "error": "Подписку нельзя отменить: прошло более 14 дней с начала действия"},
                status=status.HTTP_400_BAD_REQUEST
            )

        subscription.status = 'cancelled'
        subscription.save()
        
        return Response({
            "ok": True,
            "message": f"Подписка '{subscription.plan.name}' успешно отменена",
            "subscription": {
                "id": str(subscription.id),
                "status": subscription.status,
                "expires_at": subscription.expires_at
            }
        })

class PaymentViewSet(viewsets.ReadOnlyModelViewSet):
    """API для истории платежей"""
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        from django.db.models import Q

        try:
            from catalog.models import CinemaUser
            cinema_user = CinemaUser.objects.get(login=self.request.user.username)
            return Payment.objects.filter(
                Q(purchase__user=cinema_user) | 
                Q(subscription__user=cinema_user)
            ).select_related('purchase', 'subscription', 'purchase__content')
        except CinemaUser.DoesNotExist:
            return Payment.objects.none()
    
    def list(self, request):
        payments = self.get_queryset().order_by('-created_at')[:50]
        
        def serialize_payment(payment):
            data = {
                "id": str(payment.id),
                "txn_id": str(payment.txn_uuid),
                "amount": float(payment.amount),
                "status": payment.status,
                "paid_at": payment.paid_at,
                "created_at": payment.created_at,
                "type": None,
                "item": None
            }
            
            if payment.purchase:
                data["type"] = "content_purchase"
                data["item"] = {
                    "type": "content",
                    "id": str(payment.purchase.content_id),
                    "title": payment.purchase.content.title if payment.purchase.content else "Контент"
                }
            elif payment.subscription:
                data["type"] = "subscription"
                data["item"] = {
                    "type": "subscription",
                    "id": str(payment.subscription.id),
                    "plan_name": payment.subscription.plan.name if payment.subscription.plan else "Подписка"
                }
            
            return data
        
        return Response({
            "ok": True,
            "payments": [serialize_payment(p) for p in payments],
            "count": payments.count()
        })

class FavoriteViewSet(viewsets.ViewSet):
    """API для управления избранным"""
    permission_classes = [IsAuthenticated]
    
    def list(self, request):
        """Получить избранное пользователя"""
        from cinemaapp import services
        from cinemaapp.models import Content
        
        favorites = services.list_user_favorites(request.user)
        
        if not favorites:
            return Response({
                "ok": True,
                "favorites": [],
                "count": 0
            })
        
        content_ids = [str(item['content_id']) for item in favorites]
        
        contents = {str(c.id): c for c in 
                   Content.objects.filter(id__in=content_ids)
                   .select_related('cover_image', 'cover_image_wide')}

        items = []
        for fav in favorites:
            content_id = str(fav['content_id'])
            content = contents.get(content_id)
            if not content:
                continue
                
            items.append({
                "content": {
                    "id": content_id,
                    "title": content.title,
                    "type": content.type,
                    "poster_url": content.cover_image.url if content.cover_image else "",
                    "backdrop_url": (content.cover_image_wide.url if getattr(content, "cover_image_wide", None) 
                                   else (content.cover_image.url if content.cover_image else "")),
                    "release_year": content.release_year,
                    "is_free": content.is_free,
                },
                "added_at": fav.get('created_at')
            })
        
        return Response({
            "ok": True,
            "favorites": items,
            "count": len(items)
        })
    
    @action(detail=True, methods=['post'])
    def toggle(self, request, pk=None):
        """Добавить/удалить из избранного"""
        from cinemaapp.models import Content
        

        try:
            content = Content.objects.get(pk=pk)
        except Content.DoesNotExist:
            return Response(
                {"ok": False, "error": "Контент не найден"},
                status=status.HTTP_404_NOT_FOUND
            )

        from cinemaapp import services
        favorites = services.list_user_favorites(request.user)
        is_favorite = any(str(item['content_id']) == str(pk) for item in favorites)
        

        new_status = not is_favorite

        try:

            from catalog import actions
            class FakeRequest:
                def __init__(self, user):
                    self.user = user
                    self.POST = {}
            
            fake_request = FakeRequest(request.user)
            response = actions.toggle_favorite(fake_request, pk)
            
            if response.status_code == 200:
                return Response({
                    "ok": True,
                    "is_favorite": new_status,
                    "message": "Добавлено в избранное" if new_status else "Удалено из избранного"
                })
            else:
                return Response({
                    "ok": False,
                    "error": "Не удалось изменить избранное"
                }, status=response.status_code)
                
        except Exception as e:
            return Response({
                "ok": False,
                "error": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=True, methods=['get'])
    def status(self, request, pk=None):
        """Проверить статус избранного"""
        from cinemaapp import services
        
        favorites = services.list_user_favorites(request.user)
        is_favorite = any(str(item['content_id']) == str(pk) for item in favorites)
        
        return Response({
            "ok": True,
            "is_favorite": is_favorite
        })

from rest_framework.views import APIView

class MeView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """Полная информация о пользователе"""
        from cinemaapp import services
        from accounts.models import Profile
        
        user = request.user

        data = {
            "ok": True,
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "is_active": user.is_active,
                "date_joined": user.date_joined,
            }
        }
        

        try:
            profile = Profile.objects.get(user=user)
            data["user"]["phone"] = profile.phone
        except Profile.DoesNotExist:
            data["user"]["phone"] = None
        

        subscription_info = services.get_user_subscription_info(user)
        data["subscription"] = subscription_info
        

        purchases = services.list_user_purchases(user)
        ratings = services.list_user_ratings(user)
        history = services.list_user_history(user)
        favorites = services.list_user_favorites(user)
        
        data["stats"] = {
            "purchases_count": len(purchases),
            "ratings_count": len(ratings),
            "history_count": len(history),
            "favorites_count": len(favorites),
        }
        
        return Response(data)

class MeDetailsView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request, detail_type):
        """Получение деталей: purchases, ratings, history, favorites"""
        from cinemaapp import services
        from cinemaapp.models import Content
        
        if detail_type not in ["purchases", "ratings", "history", "favorites"]:
            return Response({"ok": False, "error": "Invalid detail type"}, 
                          status=status.HTTP_400_BAD_REQUEST)
        
        if detail_type == "purchases":
            raw_data = services.list_user_purchases(request.user)
        elif detail_type == "ratings":
            raw_data = services.list_user_ratings(request.user)
        elif detail_type == "history":
            raw_data = services.list_user_history(request.user)
        else:
            raw_data = services.list_user_favorites(request.user)
        
        if not raw_data:
            return Response({
                "ok": True,
                "type": detail_type,
                "items": [],
                "count": 0
            })

        content_ids = []
        for item in raw_data:
            try:
                content_ids.append(str(item['content_id']))
            except (KeyError, TypeError):
                continue
        
 
        contents = {}
        if content_ids:
            for c in Content.objects.filter(id__in=content_ids).select_related('cover_image'):
                contents[str(c.id)] = c
        

        items = []
        for item in raw_data:
            try:
                content_id = str(item['content_id'])
            except (KeyError, TypeError):
                continue
                
            content = contents.get(content_id)
            if not content:
                continue
                
            item_data = {
                "content": {
                    "id": str(content.id),
                    "title": content.title,
                    "type": content.type,
                    "poster_url": content.cover_image.url if content.cover_image else "",
                    "release_year": content.release_year,
                },
                "metadata": {}
            }
            
            if detail_type == "purchases":
                item_data["metadata"]["purchased_at"] = item.get('purchased_at')
            elif detail_type == "ratings":
                item_data["metadata"]["rating"] = item.get('rating')
                item_data["metadata"]["updated_at"] = item.get('updated_at')
            elif detail_type == "history":
                item_data["metadata"]["viewed_at"] = item.get('viewed_at')
            elif detail_type == "favorites":
                item_data["metadata"]["created_at"] = item.get('created_at')
            
            items.append(item_data)
        
        return Response({
            "ok": True,
            "type": detail_type,
            "items": items,
            "count": len(items)
        })